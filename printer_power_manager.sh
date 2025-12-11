#!/bin/sh

# 🖨️ Printer Power Manager - Bash Controller
# Зручний інтерфейс для запуску на принтері

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/printer_power_manager_standalone.py"
LOG_FILE="$SCRIPT_DIR/printer_power_manager.log"
PID_FILE="$SCRIPT_DIR/printer_power_manager.pid"

# Функции
print_header() {
    echo "========================================"
    echo "🖨️  PRINTER POWER MANAGER"
    echo "========================================"
}

print_success() {
    echo "✅ $1"
}

print_error() {
    echo "❌ $1"
}

print_warning() {
    echo "⚠️  $1"
}

print_info() {
    echo "ℹ️  $1"
}

# Перевірити Python
check_python() {
    if ! command -v python3 >/dev/null 2>&1; then
        print_error "Python3 не встановлено!"
        echo "Встанови: sudo apt-get install python3"
        exit 1
    fi
    
    if ! python3 -c "import requests" 2>/dev/null; then
        print_error "Модуль 'requests' не встановлено!"
        echo "Встанови: pip3 install requests"
        exit 1
    fi
    
    print_success "Python3 готов"
}

# Перевірити скрипт
check_script() {
    if [ ! -f "$PYTHON_SCRIPT" ]; then
        print_error "Скрипт $PYTHON_SCRIPT не знайден!"
        exit 1
    fi
    print_success "Скрипт знайден"
}

# Показати статус
show_status() {
    print_header
    
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            print_success "Сервіс ЗАПУЩЕНО (PID: $PID)"
        else
            print_warning "PID файл існує, але процес мертвий"
            rm -f "$PID_FILE"
        fi
    else
        print_warning "Сервіс НЕ ЗАПУЩЕНО"
    fi
    
    echo ""
    echo "📊 Останні логи:"
    if [ -f "$LOG_FILE" ]; then
        tail -n 10 "$LOG_FILE"
    else
        print_info "Логи ще не створено"
    fi
}

# Запустити демон
start_daemon() {
    print_header
    
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            print_error "Сервіс вже запущено (PID: $PID)"
            exit 1
        fi
    fi
    
    print_info "Запускаю сервіс..."
    
    nohup python3 "$PYTHON_SCRIPT" >>"$LOG_FILE" 2>&1 &
    NEW_PID=$!
    
    echo $NEW_PID >"$PID_FILE"
    
    sleep 2
    
    if kill -0 $NEW_PID 2>/dev/null; then
        print_success "Сервіс запущено (PID: $NEW_PID)"
        print_info "Логи: tail -f $LOG_FILE"
    else
        print_error "Помилка запуску!"
        cat "$LOG_FILE"
        exit 1
    fi
}

# Зупинити демон
stop_daemon() {
    print_header
    
    if [ ! -f "$PID_FILE" ]; then
        print_warning "Сервіс не запущено"
        return
    fi
    
    PID=$(cat "$PID_FILE")
    
    if ! kill -0 "$PID" 2>/dev/null; then
        print_warning "Процес мертвий, очищаю..."
        rm -f "$PID_FILE"
        return
    fi
    
    print_info "Зупиняю сервіс (PID: $PID)..."
    kill $PID
    
    # Чекаємо завершення
    for i in 1 2 3 4 5 6 7 8 9 10; do
        if ! kill -0 "$PID" 2>/dev/null; then
            print_success "Сервіс зупинено"
            rm -f "$PID_FILE"
            return
        fi
        sleep 1
    done
    
    print_warning "Примусово завершаю..."
    kill -9 $PID 2>/dev/null || true
    rm -f "$PID_FILE"
    print_success "Сервіс примусово завершено"
}

# Перезапустити
restart_daemon() {
    print_header
    print_info "Перезапускаю сервіс..."
    stop_daemon
    sleep 1
    start_daemon
}

# Показати логи
show_logs() {
    print_header
    
    if [ ! -f "$LOG_FILE" ]; then
        print_warning "Логи ще не створено"
        return
    fi
    
    print_info "Показую логи (Ctrl+C для виходу)..."
    echo ""
    tail -f "$LOG_FILE"
}

# Тест конфігурації
test_config() {
    print_header
    
    check_python
    check_script
    
    print_info "Тестую конфігурацію..."
    python3 "$PYTHON_SCRIPT" once
    
    print_success "Тест завершено успішно!"
}

# Тест паузи / резюме
test_pause() {
    print_header
    
    check_python
    check_script
    
    print_warning "⏸️  ТЕСТ PAUSE/RESUME"
    print_info "Тест включить паузу, чекатиме 60 секунд, потім RESUME"
    echo ""
    
    python3 "$PYTHON_SCRIPT" test_pause
    
    print_success "Тест PAUSE/RESUME завершено!"
}

# Меню
show_menu() {
    echo ""
    echo "Виберіть дію:"
    echo "  1) Статус"
    echo "  2) Запустити"
    echo "  3) Зупинити"
    echo "  4) Перезапустити"
    echo "  5) Логи"
    echo "  6) Тест конфігурації"
    echo "  7) Тест PAUSE/RESUME"
    echo "  0) Вихід"
    echo ""
    printf "Вибір [0-7]: "
    read -r choice
    
    case $choice in
        1) show_status ;;
        2) start_daemon ;;
        3) stop_daemon ;;
        4) restart_daemon ;;
        5) show_logs ;;
        6) test_config ;;
        7) test_pause ;;
        0) exit 0 ;;
        *) print_error "Невірний вибір!" ;;
    esac
}

# Main
main() {
    if [ $# -eq 0 ]; then
        show_menu
        main
    else
        case $1 in
            status) show_status ;;
            start) check_python && check_script && start_daemon ;;
            stop) stop_daemon ;;
            restart) check_python && check_script && restart_daemon ;;
            logs) show_logs ;;
            test) check_python && check_script && test_config ;;
            test_pause) check_python && check_script && test_pause ;;
            *)
                echo "Використання:"
                echo "  $0              - Інтерактивне меню"
                echo "  $0 status       - Показати статус"
                echo "  $0 start        - Запустити"
                echo "  $0 stop         - Зупинити"
                echo "  $0 restart      - Перезапустити"
                echo "  $0 logs         - Показати логи"
                echo "  $0 test         - Тест конфігурації"
                echo "  $0 test_pause   - Тест PAUSE/RESUME"
                ;;
        esac
    fi
}

main "$@"
