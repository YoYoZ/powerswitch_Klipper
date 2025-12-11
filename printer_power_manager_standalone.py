#!/usr/bin/env python3
"""
🖨️ 3D Printer Power Manager for DTEK (Standalone Version)
Без Docker, просто Python скрипт для запуска на принтере

Особенности:
- wait_before: сколько минут ждать перед отключением
- wait_after: сколько минут ждать ПОСЛЕ паузы перед RESUME
- Простая конфигурация в начале файла
- Логирование ТОЛЬКО в файл (без дублирования)
- Простые HTTP GET запросы (без JSON-RPC)
- Включение нагревателей перед RESUME
- Припаркування на 40°C вместо полного отключения
- test_pause режим для тестирования
- Адаптивный таймаут (90 сек для RESUME)
"""

import requests
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from pathlib import Path
from urllib.parse import quote

# ========== КОНФИГУРАЦИЯ ==========

# Moonraker base URL
MOONRAKER_BASE = "http://127.0.0.1:7125"

# ДТЕК для Киева (регіон 25, ДСО 902)
DTEK_API = "https://app.yasno.ua/api/blackout-service/public/shutdowns/regions/25/dsos/902/planned-outages"

# Твоя група ДТЕК (1.1-6.2)
PRINTER_GROUP = "1.1"

# Интервал проверки (в секундах)
CHECK_INTERVAL = 60

# Сколько минут ждать ПЕРЕД отключением
WAIT_BEFORE = 5

# Сколько минут ждать ПІСЛЯ паузы перед RESUME
WAIT_AFTER = 10

# ===== ТЕМПЕРАТУРЫ (настрой под свой пластик!) =====
# Для PLA: EXTRUDER_TEMP=200, BED_TEMP=60
# Для PETG: EXTRUDER_TEMP=245, BED_TEMP=80
# Для ABS: EXTRUDER_TEMP=240, BED_TEMP=100
EXTRUDER_TEMP = 200  # 🔥 Температура екструдера (°C)
BED_TEMP = 60        # 🛏️ Температура столу (°C)

# Логирование ТОЛЬКО в файл (без дублирования на stdout)
LOG_FILE = Path("printer_power_manager.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE)
    ]
)
logger = logging.getLogger(__name__)


class DTEKOutageManager:
    """Менеджер для роботи з графіком відключень ДТЕК"""

    def __init__(self, group: str = "1.1"):
        self.group = group
        self.outages: Dict[str, List[Tuple[float, float]]] = {}
        self.last_update = None
        logger.info(f"🔌 DTEKOutageManager ініціалізовано для групи {group}")

    def fetch_outages(self) -> bool:
        """Отримати графік відключень з API ДТЕК"""
        try:
            logger.info(f"📡 Завантажую розклад з ДТЕК...")
            response = requests.get(DTEK_API, timeout=10)
            response.raise_for_status()

            data = response.json()

            if self.group not in data:
                logger.error(f"❌ Група {self.group} не знайдена в API")
                return False

            group_data = data[self.group]

            # Парсимо today і tomorrow
            self.outages = {
                "today": self._parse_slots(group_data.get("today", {}).get("slots", [])),
                "tomorrow": self._parse_slots(group_data.get("tomorrow", {}).get("slots", []))
            }

            self.last_update = datetime.now()
            logger.info(f"✅ Розклад оновлено")
            for period in ["today", "tomorrow"]:
                for start, end in self.outages[period]:
                    start_str = f"{int(start):02d}:{int((start % 1) * 60):02d}"
                    end_str = f"{int(end):02d}:{int((end % 1) * 60):02d}"
                    logger.info(f"   {period.upper()}: 🔴 {start_str} - {end_str}")
            return True

        except Exception as e:
            logger.error(f"❌ Помилка завантаження ДТЕК: {e}")
            return False

    @staticmethod
    def _parse_slots(slots: List[Dict]) -> List[Tuple[float, float]]:
        """Парсимо слоти (беремо ТІЛЬКИ Definite)"""
        outages = []
        for slot in slots:
            if slot.get("type") == "Definite":
                start_minutes = slot.get("start", 0)
                end_minutes = slot.get("end", 0)

                start_hours = start_minutes / 60
                end_hours = end_minutes / 60

                outages.append((start_hours, end_hours))

        return outages

    def get_current_period(self) -> str:
        """Визначити сьогодні чи завтра"""
        now = datetime.now()
        if now.hour == 23:
            return "tomorrow"
        return "today"

    def get_next_danger_window(self) -> Tuple[bool, Optional[str], Optional[float]]:
        """
        Перевірити найближче небезпечне вікно з урахуванням WAIT_BEFORE
        Повертає:
        - is_approaching: чи ЗАРАЗ треба паузити (залишилось <= 1 хвилина до точки паузи)
        - window_name: назва вікна (напр. "16:00-19:00")
        - minutes_until_pause: хвилини до ТОЧКИ ПАУЗИ (не до початку вікна!)
        """
        now = datetime.now()
        current_hour = now.hour + now.minute / 60

        period = self.get_current_period()
        outages = self.outages.get(period, [])

        for start, end in outages:
            # Точка паузи = WAIT_BEFORE хвилин ДО початку вікна
            pause_point = start - (WAIT_BEFORE / 60)
            
            window_name = f"{int(start):02d}:{int((start % 1) * 60):02d}-{int(end):02d}:{int((end % 1) * 60):02d}"

            # Якщо ми ще ПЕРЕД точкою паузи
            if current_hour < pause_point:
                minutes_until_pause = (pause_point - current_hour) * 60
                
                # Якщо залишилось <= 1 хвилина - поставити паузу ЗАРАЗ
                if minutes_until_pause <= 1.0:
                    return True, window_name, minutes_until_pause
                
                # Інакше - ще не час паузи
                return False, None, None

            # Якщо ми ВЖЕ в точці паузи або в самому вікні
            elif current_hour < end:
                # Ми вже повинні бути на паузі!
                minutes_until_end = (end - current_hour) * 60
                return True, window_name, minutes_until_end
            
            # Інакше - це вікно вже закінчилось, переходимо до наступного

        return False, None, None


class MoonrakerClient:
    """Клієнт для керування принтером через Moonraker HTTP API"""

    def __init__(self, base_url: str = MOONRAKER_BASE):
        self.base_url = base_url
        self.session = requests.Session()
        logger.info(f"🖨️  Moonraker: {base_url}")

    def _call_script(self, script: str) -> bool:
        """Выполнить gcode скрипт через HTTP GET"""
        try:
            url = f"{self.base_url}/printer/gcode/script?script={quote(script)}"
            logger.debug(f"  URL: {url}")
            
            # Разные таймауты для разных команд
            # RESUME может ждать прогрева экструдера - до 90 секунд
            # Остальное - 15 секунд
            if "RESUME" in script or "M104" in script or "M140" in script:
                timeout = 90
            else:
                timeout = 15
            
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()
            
            logger.debug(f"  Status: {response.status_code}")
            return True

        except Exception as e:
            logger.error(f"❌ Помилка виконання скрипту '{script}': {e}")
            return False

    def pause_print(self) -> bool:
        """Поставити друк на паузу"""
        logger.warning("⏸️  ПАУЗУ ДРУК!")
        return self._call_script("PAUSE")

    def resume_print(self) -> bool:
        """Відновити друк (з включенням нагрівачів)"""
        logger.info("▶️  ВІДНОВЛЮЮ ДРУК!")
        
        # 1. Спочатку включаємо нагрівачі
        logger.info(f"🔥 Включаю нагрівачі: екструдер {EXTRUDER_TEMP}°C, стіл {BED_TEMP}°C")
        gcode_heat = f"M104 S{EXTRUDER_TEMP}\nM140 S{BED_TEMP}"
        if not self._call_script(gcode_heat):
            logger.warning("⚠️  Помилка при включенні нагрівачів")
            return False
        
        # 2. Чекаємо поки нагрівачі прогріються (до 90 сек)
        logger.info("⏳ Чекаю прогрів нагрівачів (до 90 сек)...")
        time.sleep(2)
        
        # 3. Робимо RESUME
        logger.info("▶️  Запускаю RESUME...")
        return self._call_script("RESUME")

    def set_heaters_off(self) -> bool:
        """Припаркувати принтер - охолодити до 40°C"""
        logger.warning("🌡️  Припаркую принтер (охолодження до 40°C)...")
        # Припаркування: екструдер 40°C, стіл 40°C (не повна паузиця)
        gcode = "M140 S40\nM104 S40"
        return self._call_script(gcode)


class PrinterPowerManager:
    """Основний менеджер керування живленням принтера"""

    def __init__(self):
        self.dtek = DTEKOutageManager(PRINTER_GROUP)
        self.moonraker = MoonrakerClient(MOONRAKER_BASE)
        self.is_paused = False
        self.pause_start_time = None
        self.current_outage = None

        logger.info(f"🖨️  PrinterPowerManager запущено")
        logger.info(f"⚙️  wait_before={WAIT_BEFORE} хвилин, wait_after={WAIT_AFTER} хвилин")
        logger.info(f"🔥 Температури: екструдер {EXTRUDER_TEMP}°C, стіл {BED_TEMP}°C")
        logger.info(f"🛏️  Припаркування: 40°C (середня температура)")
        logger.info(f"📍 Moonraker: {MOONRAKER_BASE}")

    def update_outages(self) -> None:
        """Оновити розклад відключень (в 00:00)"""
        self.dtek.fetch_outages()

    def check_and_manage(self) -> None:
        """Основна функція - перевіряти та керувати принтером"""
        
        is_approaching, window_name, minutes_until = self.dtek.get_next_danger_window()

        if is_approaching and not self.is_paused:
            # ===== РЕЖИМ 1: PAUSE =====
            logger.critical(f"⚠️  НЕБЕЗПЕЧНЕ ВІКНО БЛИЗЬКО: {window_name}")
            logger.critical(f"🛑 Ставлю друк на паузу (wait_before={WAIT_BEFORE} хвилин)")

            if self.moonraker.pause_print():
                self.is_paused = True
                self.pause_start_time = datetime.now()
                self.current_outage = window_name

                time.sleep(1)
                self.moonraker.set_heaters_off()

                logger.warning(f"⏸️  Друк на паузі")
                logger.info(f"📍 RESUME буде через {WAIT_AFTER} хвилин")

        elif self.is_paused:
            # ===== РЕЖИМ 2: ЧЕКАЄМО WAIT_AFTER =====
            time_paused = (datetime.now() - self.pause_start_time).total_seconds() / 60

            if time_paused >= WAIT_AFTER:
                # Час вийшов - робимо RESUME
                logger.info(f"✅ wait_after={WAIT_AFTER} хвилин пройшло!")
                logger.info(f"▶️  Намагаюсь RESUME...")

                if self.moonraker.resume_print():
                    self.is_paused = False
                    self.pause_start_time = None
                    self.current_outage = None
                    logger.info("✅ Друк успішно відновлено!")
                else:
                    logger.warning("⚠️  RESUME не вдав, буду спробувати ще раз")
            else:
                # Ще чекаємо
                minutes_left_wait = WAIT_AFTER - time_paused
                logger.debug(f"⏳ На паузі {time_paused:.1f} хв з {WAIT_AFTER}. Чекаю ще {minutes_left_wait:.1f} хв")

    def run_daemon(self) -> None:
        """Запустити у режимі демона (постійна робота)"""
        logger.info("🚀 Запускаю PrinterPowerManager демон...")
        logger.info(f"📍 Група ДТЕК: {PRINTER_GROUP}")

        self.update_outages()

        next_update = self._get_next_midnight()

        while True:
            try:
                current_time = datetime.now()

                if current_time >= next_update:
                    logger.info("🔄 Оновлюю розклад о 00:00...")
                    self.update_outages()
                    next_update = self._get_next_midnight()

                self.check_and_manage()

                time.sleep(CHECK_INTERVAL)

            except KeyboardInterrupt:
                logger.info("⏹️  PrinterPowerManager зупинено")
                break
            except Exception as e:
                logger.error(f"❌ Помилка в main loop: {e}")
                time.sleep(CHECK_INTERVAL)

    @staticmethod
    def _get_next_midnight() -> datetime:
        """Отримати час наступної ночи 00:00"""
        now = datetime.now()
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)

    def run_once(self) -> None:
        """Запустити один раз (для cron)"""
        print("=" * 40)
        print("🖨️  PRINTER POWER MANAGER")
        print("=" * 40)
        self.update_outages()
        self.check_and_manage()
        print("✅ Тест завершено успішно!")

    def test_pause_resume(self) -> None:
        """Тест: PAUSE -> чекаємо 60 сек -> RESUME"""
        print("=" * 40)
        print("🖨️  PRINTER POWER MANAGER - TEST PAUSE/RESUME")
        print("=" * 40)
        
        print("\n1️⃣  ЗАПУСКАЮ PAUSE...")
        if self.moonraker.pause_print():
            print("✅ PAUSE успішно!")
        else:
            print("❌ PAUSE не вдав!")
            return
        
        time.sleep(1)
        if self.moonraker.set_heaters_off():
            print("✅ Принтер припаркований (40°C)")
        else:
            print("❌ Помилка при припаркуванні")
        
        print("\n2️⃣  ЧЕКАЮ 60 СЕКУНД...")
        for i in range(60, 0, -1):
            if i % 10 == 0 or i <= 5:
                print(f"⏳ Залишилось {i} сек...")
            time.sleep(1)
        
        print("\n3️⃣  ЗАПУСКАЮ RESUME...")
        if self.moonraker.resume_print():
            print("✅ RESUME успішно!")
            print("\n✅ Тест PAUSE/RESUME завершено успішно!")
        else:
            print("❌ RESUME не вдав!")


def main():
    """Entry point"""
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "once":
            manager = PrinterPowerManager()
            manager.run_once()
        elif sys.argv[1] == "test_pause":
            manager = PrinterPowerManager()
            manager.test_pause_resume()
    else:
        manager = PrinterPowerManager()
        manager.run_daemon()


if __name__ == "__main__":
    main()
