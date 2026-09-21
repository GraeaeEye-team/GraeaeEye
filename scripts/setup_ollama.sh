#!/usr/bin/env bash
# ==============================================================================
# GraeaeEye: Интерактивный установщик и менеджер локальной нейросети Ollama
# ==============================================================================
set -e

# Определение корня проекта с поддержкой запуска через симлинк и напрямую
get_project_root() {
    if git rev-parse --show-toplevel >/dev/null 2>&1; then
        git rev-parse --show-toplevel
        return
    fi
    local target_path
    target_path="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")"
    local target_dir
    target_dir="$(cd "$(dirname "$target_path")" && pwd)"
    if [ -f "$target_dir/.env" ] || [ -f "$target_dir/docker-compose.yml" ] || [ -f "$target_dir/.env.example" ]; then
        echo "$target_dir"
    elif [ -f "$target_dir/../.env" ] || [ -f "$target_dir/../docker-compose.yml" ] || [ -f "$target_dir/../.env.example" ]; then
        echo "$(cd "$target_dir/.." && pwd)"
    else
        pwd
    fi
}

PROJECT_ROOT="$(get_project_root)"
ENV_FILE="$PROJECT_ROOT/.env"

# Цвета для вывода в терминале
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "${CYAN}${BOLD}"
echo "======================================================================"
echo "    GraeaeEye Underwriting Engine: Настройка локальной Ollama LLM     "
echo "======================================================================"
echo -e "${NC}"

# ------------------------------------------------------------------------------
# 1. Чтение текущей конфигурации из .env (если есть)
# ------------------------------------------------------------------------------
CURRENT_MODEL="llama3.2:1b"
CURRENT_PORT="11434"

if [ -f "$ENV_FILE" ]; then
    ENV_MODEL=$(grep -E '^LLM_MODEL=' "$ENV_FILE" | cut -d '=' -f2- | tr -d ' "' || true)
    ENV_HOST=$(grep -E '^OLLAMA_HOST=' "$ENV_FILE" | cut -d '=' -f2- | tr -d ' "' || true)
    [ -n "$ENV_MODEL" ] && CURRENT_MODEL="$ENV_MODEL"
    if [ -n "$ENV_HOST" ]; then
        # Извлекаем порт из OLLAMA_HOST (например, http://...:11434)
        EXTRACTED_PORT=$(echo "$ENV_HOST" | grep -oE '[0-9]+$' || true)
        [ -n "$EXTRACTED_PORT" ] && CURRENT_PORT="$EXTRACTED_PORT"
    fi
fi

# ------------------------------------------------------------------------------
# 2. Проверка наличия бинарника Ollama
# ------------------------------------------------------------------------------
echo -e "${BOLD}[Шаг 1/5] Проверка окружения Ollama...${NC}"

if ! command -v ollama >/dev/null 2>&1; then
    echo -e "${YELLOW}Ollama не найдена в системе.${NC}"
    read -r -p "Хотите установить Ollama сейчас? [y/N]: " INSTALL_CHOICE
    case "$INSTALL_CHOICE" in
        [yY]|[yY][eE][sS])
            echo -e "${BLUE}Установка Ollama через официальный установщик...${NC}"
            curl -fsSL https://ollama.com/install.sh | sh
            ;;
        *)
            echo -e "${RED}Установка отменена. Для работы с локальной LLM установите Ollama вручную: https://ollama.ai${NC}"
            exit 1
            ;;
    esac
else
    echo -e "${GREEN}✓ Ollama уже установлена:${NC} $(which ollama)"
fi

# ------------------------------------------------------------------------------
# 3. Интерактивный выбор модели нейросети
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[Шаг 2/5] Выбор модели нейросети:${NC}"
echo "  1) llama3.2:1b  [Рекомендуется] (~1.3 ГБ) — ультрабыстрая, мгновенный инференс даже на CPU"
echo "  2) llama3:8b    (~4.7 ГБ) — глубокий синтез, требует больше RAM/VRAM"
echo "  3) Использовать модель из .env (${CURRENT_MODEL})"
echo "  4) Ввести свое название модели (например, qwen2.5:3b, mistral, phi3)"

read -r -p "Выберите вариант [1-4] (по умолчанию: 1): " MODEL_OPTION

case "$MODEL_OPTION" in
    2)
        CHOSEN_MODEL="llama3:8b"
        ;;
    3)
        CHOSEN_MODEL="$CURRENT_MODEL"
        ;;
    4)
        read -r -p "Введите тег модели Ollama: " CUSTOM_MODEL
        CHOSEN_MODEL="${CUSTOM_MODEL:-llama3.2:1b}"
        ;;
    *)
        CHOSEN_MODEL="llama3.2:1b"
        ;;
esac

echo -e "${GREEN}✓ Выбрана модель:${NC} ${BOLD}${CHOSEN_MODEL}${NC}"

# ------------------------------------------------------------------------------
# 4. Проверка и выбор свободного порта
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[Шаг 3/5] Проверка сетевого порта...${NC}"

is_port_in_use() {
    local port=$1
    if command -v lsof >/dev/null 2>&1; then
        lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1 && return 0
    fi
    if command -v ss >/dev/null 2>&1; then
        ss -tulpn | grep -q ":$port " && return 0
    fi
    return 1
}

TARGET_PORT="$CURRENT_PORT"
ALREADY_RUNNING=false

if is_port_in_use "$TARGET_PORT"; then
    # Проверяем, не отвечает ли на этом порту уже сама Ollama
    if curl -s -m 2 "http://127.0.0.1:$TARGET_PORT/api/tags" >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Сервер Ollama уже активен на порту ${TARGET_PORT}.${NC}"
        ALREADY_RUNNING=true
    else
        echo -e "${YELLOW}Порт ${TARGET_PORT} занят другим приложением.${NC}"
        # Ищем следующий свободный порт
        CANDIDATE_PORT=$((TARGET_PORT + 1))
        while is_port_in_use "$CANDIDATE_PORT"; do
            CANDIDATE_PORT=$((CANDIDATE_PORT + 1))
        done

        read -r -p "Использовать свободный порт ${CANDIDATE_PORT}? [Y/n]: " PORT_CHOICE
        case "$PORT_CHOICE" in
            [nN]|[nN][oO])
                read -r -p "Введите номер порта вручную: " MANUAL_PORT
                TARGET_PORT="${MANUAL_PORT:-$CANDIDATE_PORT}"
                ;;
            *)
                TARGET_PORT="$CANDIDATE_PORT"
                ;;
        esac
    fi
else
    echo -e "${GREEN}✓ Порт ${TARGET_PORT} свободен.${NC}"
fi

# ------------------------------------------------------------------------------
# 5. Запуск сервера Ollama (если еще не запущен)
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[Шаг 4/5] Запуск демона Ollama...${NC}"

PID_FILE="$PROJECT_ROOT/.ollama.pid"

if [ "$ALREADY_RUNNING" = true ]; then
    echo -e "${GREEN}✓ Сервер уже работает на порту ${TARGET_PORT}.${NC}"
    # Проверяем, запущен ли сервис через systemd и слушает ли 0.0.0.0
    if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet ollama 2>/dev/null; then
        if ! systemctl show ollama --property=Environment 2>/dev/null | grep -q "OLLAMA_HOST=0.0.0.0"; then
            echo -e "${YELLOW}Ollama запущена через systemd, но слушает только 127.0.0.1 (контейнеры Docker не смогут подключиться).${NC}"
            echo -e "${BLUE}Настройка systemd override для привязки к 0.0.0.0:${TARGET_PORT}...${NC}"
            sudo mkdir -p /etc/systemd/system/ollama.service.d
            echo -e "[Service]\nEnvironment=\"OLLAMA_HOST=0.0.0.0:${TARGET_PORT}\"" | sudo tee /etc/systemd/system/ollama.service.d/override.conf >/dev/null
            sudo systemctl daemon-reload
            sudo systemctl restart ollama
            echo -e "${GREEN}✓ Сервис Ollama перезапущен с привязкой к 0.0.0.0:${TARGET_PORT}!${NC}"
        fi
    fi
else
    echo -e "${BLUE}Запуск сервера: OLLAMA_HOST=0.0.0.0:${TARGET_PORT} ollama serve...${NC}"
    # Привязываем к 0.0.0.0, чтобы Docker контейнеры могли подключаться через host-gateway
    OLLAMA_HOST="0.0.0.0:${TARGET_PORT}" nohup ollama serve > "$PROJECT_ROOT/ollama.log" 2>&1 &
    OLLAMA_PID=$!
    echo "$OLLAMA_PID" > "$PID_FILE"

    echo "Ожидание готовности сервера..."
    READY=false
    for i in {1..20}; do
        if curl -s -m 1 "http://127.0.0.1:${TARGET_PORT}/api/tags" >/dev/null 2>&1; then
            READY=true
            break
        fi
        sleep 1
    done

    if [ "$READY" = true ]; then
        echo -e "${GREEN}✓ Сервер Ollama успешно запущен на порту ${TARGET_PORT} (PID: ${OLLAMA_PID})!${NC}"
    else
        echo -e "${RED}Ошибка запуска Ollama. Подробности в ${PROJECT_ROOT}/ollama.log${NC}"
        exit 1
    fi
fi

# ------------------------------------------------------------------------------
# 6. Проверка и скачивание модели
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[Шаг 5/5] Загрузка весов модели ${CHOSEN_MODEL}...${NC}"

# Проверяем, загружена ли модель в Ollama
OLLAMA_CHECK_HOST="http://127.0.0.1:${TARGET_PORT}"
MODELS_LIST=$(OLLAMA_HOST="$OLLAMA_CHECK_HOST" ollama list 2>/dev/null || true)

if echo "$MODELS_LIST" | grep -q "$CHOSEN_MODEL"; then
    echo -e "${GREEN}✓ Модель ${CHOSEN_MODEL} уже загружена на хосте.${NC}"
else
    echo -e "${YELLOW}Модель ${CHOSEN_MODEL} не найдена в локальном кэше.${NC}"
    read -r -p "Скачать модель ${CHOSEN_MODEL} сейчас? [Y/n]: " PULL_CHOICE
    case "$PULL_CHOICE" in
        [nN]|[nN][oO])
            echo -e "${YELLOW}Скачивание пропущено. Модель можно загрузить позже командой:${NC}"
            echo "  OLLAMA_HOST=${OLLAMA_CHECK_HOST} ollama pull ${CHOSEN_MODEL}"
            ;;
        *)
            echo -e "${BLUE}Скачивание ${CHOSEN_MODEL} (сохраняется на ваш диск в ~/.ollama)...${NC}"
            OLLAMA_HOST="$OLLAMA_CHECK_HOST" ollama pull "$CHOSEN_MODEL"
            echo -e "${GREEN}✓ Модель ${CHOSEN_MODEL} успешно скачана!${NC}"
            ;;
    esac
fi

# ------------------------------------------------------------------------------
# 7. Автоматическое обновление .env
# ------------------------------------------------------------------------------
DOCKER_OLLAMA_HOST="http://host.docker.internal:${TARGET_PORT}"

echo -e "\n${BOLD}======================================================================${NC}"
echo -e "${BOLD}Автоматическое применение параметров в конфиг .env:${NC}"

if [ ! -f "$ENV_FILE" ] && [ -f "$PROJECT_ROOT/.env.example" ]; then
    cp "$PROJECT_ROOT/.env.example" "$ENV_FILE"
    echo -e "${BLUE}Файл .env создан на основе .env.example.${NC}"
fi

if [ -f "$ENV_FILE" ]; then
    update_env_var() {
        local key=$1
        local val=$2
        if grep -qE "^#?${key}=" "$ENV_FILE"; then
            sed -i "s|^#\?${key}=.*|${key}=${val}|" "$ENV_FILE"
        else
            echo "${key}=${val}" >> "$ENV_FILE"
        fi
    }

    update_env_var "LLM_PROVIDER" "ollama"
    update_env_var "LLM_MODEL" "$CHOSEN_MODEL"
    update_env_var "OLLAMA_HOST" "$DOCKER_OLLAMA_HOST"

    echo "  LLM_PROVIDER: ${BOLD}ollama${NC}"
    echo "  LLM_MODEL:    ${BOLD}${CHOSEN_MODEL}${NC}"
    echo "  OLLAMA_HOST:  ${BOLD}${DOCKER_OLLAMA_HOST}${NC} (доступ из Docker к хосту)"
    echo -e "${GREEN}✓ Файл .env успешно обновлен!${NC}"
else
    echo -e "${YELLOW}Предупреждение: файл .env не найден.${NC}"
fi

# ------------------------------------------------------------------------------
# 8. Финальные инструкции по запуску Docker
# ------------------------------------------------------------------------------
echo -e "\n${GREEN}${BOLD}======================================================================${NC}"
echo -e "${GREEN}${BOLD}  ✓ Настройка завершена! Локальная нейросеть готова к работе.        ${NC}"
echo -e "${GREEN}${BOLD}======================================================================${NC}"
echo -e "Модель:           ${BOLD}${CHOSEN_MODEL}${NC}"
echo -e "Локальный порт:   ${BOLD}http://127.0.0.1:${TARGET_PORT}${NC}"
echo -e "Адрес для Docker: ${BOLD}${DOCKER_OLLAMA_HOST}${NC}"
echo ""
echo -e "${BOLD}Следующий шаг — перезапустите Docker-контейнеры:${NC}"
echo -e "  ${CYAN}sudo docker-compose up -d --build${NC}"
echo ""
echo -e "После этого откройте веб-интерфейс ${BOLD}http://localhost:8000${NC} и запустите андеррайтинг."
echo -e "Кредитный меморандум будет сгенерирован вашей локальной нейросетью!"
echo ""
echo -e "${YELLOW}Полезные команды:${NC}"
echo -e "  Посмотреть логи Ollama:  ${BOLD}tail -f ${PROJECT_ROOT}/ollama.log${NC}"
echo -e "  Остановить Ollama:       ${BOLD}kill \$(cat ${PID_FILE} 2>/dev/null) 2>/dev/null || pkill -f 'ollama serve'${NC}"
echo -e "${GREEN}======================================================================${NC}"

