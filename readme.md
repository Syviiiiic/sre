# Microservices Monitoring Demo
## Для VDS с 2CPU и 4GB RAM

### 📋 Требования
- Ubuntu 20.04/22.04
- 2 CPU ядра
- 4 GB RAM
- 10 GB свободного места

### 🚀 Быстрый старт

# 1. Дайте права
chmod +x *.sh scripts/*.sh

# 2. Установите окружение
./00-setup.sh

# 3. Разверните всё
./01-deploy-all.sh

# 4. Протестируйте
./02-access-services.sh
scripts/test-endpoints.sh

# 5. Создайте нагрузку
scripts/generate-load.sh