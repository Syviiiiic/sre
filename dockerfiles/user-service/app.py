# dockerfiles/user-service/app.py
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import random
import time
from datetime import datetime
import threading
import psycopg2
from psycopg2 import pool
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prometheus метрики
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP Requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['endpoint']
)

USERS_COUNT = Gauge(
    'app_users_total',
    'Total number of registered users'
)

DB_CONNECTIONS = Gauge(
    'db_connections_total',
    'Total database connections'
)

ERROR_COUNT = Counter(
    'http_errors_total',
    'Total HTTP errors',
    ['type']
)

# Инициализация connection pool для PostgreSQL
try:
    connection_pool = psycopg2.pool.SimpleConnectionPool(
        1, 10,
        host='postgres',
        database='microservices',
        user='admin',
        password='admin123',
        port=5432
    )
    DB_CONNECTIONS.set(10)
    logger.info("Database connection pool created")
except Exception as e:
    logger.error(f"Failed to create connection pool: {e}")
    connection_pool = None

def get_db_connection():
    """Получение соединения с БД"""
    if connection_pool:
        try:
            return connection_pool.getconn()
        except Exception as e:
            ERROR_COUNT.labels(type='db_connection').inc()
            logger.error(f"Failed to get DB connection: {e}")
    return None

def release_db_connection(conn):
    """Возврат соединения в пул"""
    if connection_pool and conn:
        connection_pool.putconn(conn)

def init_database():
    """Инициализация базы данных"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        # Создание таблицы пользователей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Создание индексов
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        
        conn.commit()
        logger.info("Database initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return False
    finally:
        release_db_connection(conn)

class MetricsHandler(BaseHTTPRequestHandler):
    """Обработчик для метрик Prometheus"""
    def do_GET(self):
        if self.path == '/metrics':
            REQUEST_COUNT.labels(method='GET', endpoint='/metrics', status='200').inc()
            self.send_response(200)
            self.send_header('Content-Type', CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(generate_latest())
        else:
            self.send_error(404)

class UserHandler(BaseHTTPRequestHandler):
    """Обработчик для API пользователей"""
    
    def _send_response(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def _send_error(self, message, status=400):
        ERROR_COUNT.labels(type='http_error').inc()
        self._send_response({'error': message}, status)
    
    def do_GET(self):
        start_time = time.time()
        
        try:
            if self.path == '/health':
                REQUEST_COUNT.labels(method='GET', endpoint='/health', status='200').inc()
                
                # Проверка подключения к БД
                db_status = 'connected' if connection_pool else 'disconnected'
                
                self._send_response({
                    'status': 'healthy',
                    'service': 'user-service',
                    'timestamp': datetime.now().isoformat(),
                    'database': db_status,
                    'version': '1.0.0'
                })
            
            elif self.path == '/users':
                REQUEST_COUNT.labels(method='GET', endpoint='/users', status='200').inc()
                conn = get_db_connection()
                if not conn:
                    self._send_error('Database unavailable', 503)
                    return
                
                try:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, name, email, created_at FROM users LIMIT 100")
                    rows = cursor.fetchall()
                    
                    users = []
                    for row in rows:
                        users.append({
                            'id': row[0],
                            'name': row[1],
                            'email': row[2],
                            'created_at': row[3].isoformat() if row[3] else None
                        })
                    
                    self._send_response({
                        'users': users,
                        'count': len(users),
                        'timestamp': datetime.now().isoformat()
                    })
                    
                    # Обновляем метрику количества пользователей
                    USERS_COUNT.set(len(users))
                    
                except Exception as e:
                    logger.error(f"Failed to fetch users: {e}")
                    self._send_error('Internal server error', 500)
                finally:
                    release_db_connection(conn)
            
            elif self.path.startswith('/users/'):
                user_id = self.path.split('/')[-1]
                REQUEST_COUNT.labels(method='GET', endpoint='/users/{id}', status='200').inc()
                
                if not user_id.isdigit():
                    self._send_error('Invalid user ID', 400)
                    return
                
                conn = get_db_connection()
                if not conn:
                    self._send_error('Database unavailable', 503)
                    return
                
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT id, name, email, created_at FROM users WHERE id = %s",
                        (int(user_id),)
                    )
                    row = cursor.fetchone()
                    
                    if row:
                        self._send_response({
                            'id': row[0],
                            'name': row[1],
                            'email': row[2],
                            'created_at': row[3].isoformat() if row[3] else None
                        })
                    else:
                        self._send_error('User not found', 404)
                        
                except Exception as e:
                    logger.error(f"Failed to fetch user {user_id}: {e}")
                    self._send_error('Internal server error', 500)
                finally:
                    release_db_connection(conn)
            
            else:
                REQUEST_COUNT.labels(method='GET', endpoint='unknown', status='404').inc()
                self._send_error('Not found', 404)
                
        finally:
            # Измеряем latency
            latency = time.time() - start_time
            endpoint = self.path.split('?')[0]  # Убираем query параметры
            REQUEST_LATENCY.labels(endpoint=endpoint).observe(latency)
    
    def do_POST(self):
        start_time = time.time()
        
        try:
            if self.path == '/users':
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length == 0:
                    self._send_error('Empty request body', 400)
                    return
                
                post_data = self.rfile.read(content_length)
                
                try:
                    data = json.loads(post_data.decode('utf-8'))
                except json.JSONDecodeError:
                    self._send_error('Invalid JSON', 400)
                    return
                
                # Валидация
                if 'name' not in data or 'email' not in data:
                    self._send_error('Name and email are required', 400)
                    return
                
                conn = get_db_connection()
                if not conn:
                    self._send_error('Database unavailable', 503)
                    return
                
                try:
                    cursor = conn.cursor()
                    
                    # Проверяем, существует ли email
                    cursor.execute(
                        "SELECT id FROM users WHERE email = %s",
                        (data['email'],)
                    )
                    if cursor.fetchone():
                        self._send_error('Email already exists', 409)
                        return
                    
                    # Создаем пользователя
                    cursor.execute(
                        "INSERT INTO users (name, email) VALUES (%s, %s) RETURNING id, created_at",
                        (data['name'], data['email'])
                    )
                    
                    user_id, created_at = cursor.fetchone()
                    conn.commit()
                    
                    REQUEST_COUNT.labels(method='POST', endpoint='/users', status='201').inc()
                    
                    self._send_response({
                        'id': user_id,
                        'name': data['name'],
                        'email': data['email'],
                        'created_at': created_at.isoformat(),
                        'message': 'User created successfully',
                        'timestamp': datetime.now().isoformat()
                    }, 201)
                    
                    # Обновляем метрику
                    USERS_COUNT.inc()
                    
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Failed to create user: {e}")
                    self._send_error('Internal server error', 500)
                finally:
                    release_db_connection(conn)
            
            else:
                REQUEST_COUNT.labels(method='POST', endpoint='unknown', status='404').inc()
                self._send_error('Not found', 404)
                
        finally:
            latency = time.time() - start_time
            REQUEST_LATENCY.labels(endpoint=self.path).observe(latency)
    
    def log_message(self, format, *args):
        # Уменьшаем логирование для чистоты вывода
        pass

def simulate_background_load():
    """Имитация фоновой нагрузки на БД"""
    while True:
        try:
            conn = get_db_connection()
            if conn:
                try:
                    cursor = conn.cursor()
                    # Простые запросы для создания нагрузки
                    cursor.execute("SELECT COUNT(*) FROM users")
                    cursor.execute("SELECT pg_sleep(0.01)")  # Легкая задержка
                    cursor.fetchall()
                finally:
                    release_db_connection(conn)
        except Exception as e:
            logger.debug(f"Background load error: {e}")
        
        time.sleep(random.uniform(0.5, 2.0))

def update_metrics_periodically():
    """Периодическое обновление метрик"""
    while True:
        try:
            if connection_pool:
                DB_CONNECTIONS.set(connection_pool.maxconn - len(connection_pool._used))
        except Exception as e:
            logger.debug(f"Metrics update error: {e}")
        
        time.sleep(30)

if __name__ == '__main__':
    logger.info("Starting User Service...")
    
    # Инициализация БД
    max_retries = 5
    for i in range(max_retries):
        logger.info(f"Attempting to initialize database (attempt {i+1}/{max_retries})...")
        if init_database():
            logger.info("Database initialized successfully")
            break
        time.sleep(5)
    else:
        logger.warning("Failed to initialize database after multiple attempts")
    
    # Запускаем фоновые задачи
    background_thread = threading.Thread(target=simulate_background_load, daemon=True)
    background_thread.start()
    
    metrics_thread = threading.Thread(target=update_metrics_periodically, daemon=True)
    metrics_thread.start()
    
    # Настраиваем HTTP сервер
    def handler(*args):
        """Роутинг запросов"""
        path = args[0].path
        if path == '/metrics':
            MetricsHandler(*args)
        else:
            UserHandler(*args)
    
    server = HTTPServer(('0.0.0.0', 8000), handler)
    logger.info("User service started on port 8000")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        if connection_pool:
            connection_pool.closeall()
        server.server_close()