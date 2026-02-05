#!/bin/bash
set -e

echo "========================================="
echo " Microservices Demo Setup for 2CPU/4GB RAM"
echo "========================================="

# Проверка прав
if [ "$EUID" -eq 0 ]; then 
  echo "Пожалуйста, не запускайте как root!"
  exit 1
fi

echo "1. Устанавливаем Docker..."
sudo apt-get update
sudo apt-get install -y docker.io curl
sudo usermod -aG docker $USER

echo "2. Устанавливаем kubectl..."
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

echo "3. Устанавливаем Minikube..."
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube

echo "4. Запускаем Minikube с оптимизацией под 4GB RAM..."
minikube start --memory=2048 --cpus=2 --disk-size=10g \
  --driver=docker \
  --extra-config=kubelet.housekeeping-interval=10s

echo "5. Включаем необходимые аддоны..."
minikube addons enable metrics-server
minikube addons enable ingress

echo "6. Включаем Docker registry в Minikube..."
minikube addons enable registry
eval $(minikube docker-env)

echo "7. Создаем Docker образы..."
echo "Создаем образ user-service..."
cd dockerfiles/user-service
docker build -t user-service:latest .
cd ../..

echo "Создаем образ api-gateway..."
cd dockerfiles/api-gateway
docker build -t api-gateway:latest .
cd ../..

echo "========================================="
echo " Установка завершена успешно!"
echo " Для продолжения запустите: ./01-deploy-all.sh"
echo "========================================="