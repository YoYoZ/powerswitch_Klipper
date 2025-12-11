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
            print("✅ Нагрівачі вимкнені")
        else:
            print("❌ Помилка при вимиканні нагрівачів")
        
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
