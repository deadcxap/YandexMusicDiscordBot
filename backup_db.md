Ниже приведён пример скрипта на sh, который можно добавить в cron. Он выполняет следующие шаги:

1. Создаёт резервную копию базы MongoDB внутри контейнера (через docker exec).
2. Копирует созданный архив с контейнера на хост.
3. Шифрует архив с помощью GPG (симметричное шифрование с алгоритмом AES256).
4. Отправляет зашифрованный файл в облако с помощью rclone.
5. Очищает временные файлы.

> **Важно:**  
> - Задайте переменные, такие как путь для бэкапов (`BACKUP_DIR`), имя удалённого хранилища для rclone (`RCLONE_DEST`), а также установите переменную окружения `ENCRYPTION_PASSPHRASE` с вашим паролем для шифрования.  
> - Убедитесь, что на хосте установлены docker, gpg и rclone, а также что контейнер MongoDB называется так же, как указано в скрипте (в примере – `ymdb-mongodb`).

Скрипт (например, сохраните его как `/usr/local/bin/backup.sh` и сделайте исполняемым):

```sh
#!/bin/sh
# backup.sh - резервное копирование базы MongoDB с шифрованием и отправкой в облако

# Настройки (отредактируйте под себя)
BACKUP_DIR="/path/to/backup"         # Локальная папка для хранения бэкапов
RCLONE_DEST="remote:backup"           # Название удалённого хранилища rclone (напр., remote:backup)
MONGO_CONTAINER="ymdb-mongodb"        # Имя контейнера MongoDB

# Получаем дату для имени файла
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="mongodb_backup_${DATE}.archive"
ENCRYPTED_FILE="${BACKUP_FILE}.gpg"

# Проверяем, задан ли пароль для шифрования
if [ -z "$ENCRYPTION_PASSPHRASE" ]; then
  echo "Переменная ENCRYPTION_PASSPHRASE не установлена. Выход."
  exit 1
fi

# Создаём папку для бэкапов, если её нет
mkdir -p "$BACKUP_DIR"

# Создание резервной копии базы данных через mongodump внутри контейнера
echo "Создаём резервную копию MongoDB..."
docker exec "$MONGO_CONTAINER" mongodump --archive="/tmp/${BACKUP_FILE}" --gzip
if [ $? -ne 0 ]; then
  echo "Ошибка при выполнении mongodump."
  exit 1
fi

# Копируем файл резервной копии с контейнера на хост
echo "Копируем резервную копию с контейнера..."
docker cp "$MONGO_CONTAINER":/tmp/"${BACKUP_FILE}" "$BACKUP_DIR"/
if [ $? -ne 0 ]; then
  echo "Ошибка при копировании файла резервной копии."
  exit 1
fi

# Очищаем временный файл резервной копии внутри контейнера
docker exec "$MONGO_CONTAINER" rm -f "/tmp/${BACKUP_FILE}"

# Шифруем резервную копию с помощью GPG
echo "Шифруем резервную копию..."
gpg --batch --yes --passphrase "$ENCRYPTION_PASSPHRASE" --symmetric --cipher-algo AES256 -o "$BACKUP_DIR"/"$ENCRYPTED_FILE" "$BACKUP_DIR"/"$BACKUP_FILE"
if [ $? -ne 0 ]; then
  echo "Ошибка при шифровании резервной копии."
  exit 1
fi

# Удаляем незашифрованный архив
rm -f "$BACKUP_DIR"/"$BACKUP_FILE"

# Отправляем зашифрованную резервную копию в облако с помощью rclone
echo "Отправляем зашифрованную резервную копию в облако..."
rclone copy "$BACKUP_DIR"/"$ENCRYPTED_FILE" "$RCLONE_DEST"
if [ $? -ne 0 ]; then
  echo "Ошибка при отправке резервной копии в облако."
  exit 1
fi

# Опционально удаляем локальный зашифрованный файл после успешной отправки
rm -f "$BACKUP_DIR"/"$ENCRYPTED_FILE"

echo "Резервное копирование и отправка в облако завершены успешно."
```

### Как использовать скрипт в cron

1. Сделайте скрипт исполняемым:

   ```bash
   chmod +x /usr/local/bin/backup.sh
   ```

2. Добавьте задание в crontab (например, ежедневное резервное копирование в 03:00):

   ```cron
   0 3 * * * /usr/local/bin/backup.sh >> /var/log/backup.log 2>&1
   ```

В итоге этот скрипт автоматизирует процесс резервного копирования базы, шифрования и отправки в облако. Не забудьте проверить и настроить пути, переменные и параметры согласно вашим требованиям.