#!/bin/bash
# Airflow 容器启动脚本：清理旧进程 → 初始化元数据库 → 创建管理员 → 启动 Web 与 Scheduler
set -e

echo "正在清理已有 Airflow 进程..."
pkill -f "airflow webserver" || true
pkill -f "airflow scheduler" || true
rm -f /opt/airflow/airflow-webserver.pid
rm -f /opt/airflow/airflow-scheduler.pid

sleep 2

echo "正在初始化 Airflow 元数据库..."
airflow db init

echo "正在创建管理员账号 admin/admin ..."
airflow users create \
    --username admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@example.com \
    --password admin || echo "管理员账号已存在，跳过"

echo "正在启动 Airflow Webserver 与 Scheduler..."
airflow webserver --port 8080 --daemon &
airflow scheduler
