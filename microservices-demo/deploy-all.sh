# 01-deploy-all.sh (полная версия)
#!/bin/bash
set -e

echo "========================================="
echo " Microservices Demo - Full Deployment"
echo "========================================="

# Проверяем Minikube
if ! minikube status | grep -q "Running"; then
  echo "Minikube не запущен. Запустите ./00-setup.sh"
  exit 1
fi

echo "1. Создаем namespace..."
kubectl apply -f manifests/00-namespace.yaml

echo "2. Развертываем PostgreSQL..."
kubectl apply -f manifests/01-postgresql/
echo "   Ждем запуска PostgreSQL..."
kubectl wait --for=condition=available --timeout=120s deployment/postgres -n microservices-demo

echo "3. Инициализируем базу данных..."
kubectl apply -f manifests/init-db-job.yaml
echo "   Ждем инициализации БД..."
kubectl wait --for=condition=complete --timeout=60s job/init-database -n microservices-demo

echo "4. Развертываем User Service..."
kubectl apply -f manifests/02-user-service/
echo "   Ждем запуска User Service..."
kubectl wait --for=condition=available --timeout=120s deployment/user-service -n microservices-demo

echo "5. Развертываем API Gateway..."
kubectl apply -f manifests/03-api-gateway/
sleep 10

echo "6. Развертываем мониторинг..."
kubectl apply -f manifests/04-monitoring/
echo "   Ждем запуска мониторинга..."
kubectl wait --for=condition=available --timeout=120s deployment/prometheus -n microservices-demo
kubectl wait --for=condition=available --timeout=120s deployment/grafana -n microservices-demo

echo "7. Запускаем генератор нагрузки..."
kubectl apply -f manifests/05-load-test/

echo "8. Настраиваем автоматическое масштабирование..."
kubectl apply -f manifests/02-user-service/hpa.yaml 2>/dev/null || echo "HPA не настроен"

echo "9. Настройка Grafana..."
sleep 30
# Импортируем дашборд
bash scripts/import-grafana-dashboard.sh

echo "10. Создаем Ingress (если включен)..."
kubectl apply -f manifests/ingress.yaml 2>/dev/null || echo "Ingress не настроен"

echo "========================================="
echo " Развертывание завершено!"
echo "========================================="
echo ""
echo "Сервисы запущены:"
kubectl get all -n microservices-demo
echo ""
echo "Для доступа запустите: ./02-access-services.sh"