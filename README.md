# 🎓 Vision Homework Platform

## 🌐 Live Demo
[https://visions-hw.kz](https://visions-hw.kz)

## 📋 Описание
**Visions-homework** — это веб-платформа для учёта и проверки домашних заданий. Система позволяет преподавателям назначать задания, а студентам — сдавать их. Также реализована внутренняя админка для проверки, управления пользователями и отображения статистики.
Сайт был разработан как дополнение к основному сайту [https://visions.kz/](https://visions.kz)

Проект создан для университета и используется в реальной практике.

## 🚀 Технологии и стек
- ⚙️ Backend: **Django**, **Django REST Framework**
- 🧩 Frontend: **HTML**, **CSS**, **Bootstrap**
- 🐘 База данных: **PostgreSQL**
- 🔐 Аутентификация: **JWT**
- 🖥️ Docker для изоляции и развёртывания
- 📩 Email-уведомления

## 🔑 Основные функции
- Регистрация и логин
- Кабинеты студентов
- Назначение и сдача заданий
- Проверка домашних работ с комментариями
- Админка для модерации пользователей и заданий
- Уведомления, фильтры и сортировки

## 📸 Скриншоты

### 🏆 Рейтинг пользователей
![image](https://github.com/user-attachments/assets/0ccd73af-0454-4ac2-86b2-26c50ae589ac)


### 👤 Профиль пользователя
![image](https://github.com/user-attachments/assets/44bf0784-0d96-490a-a16d-04f0a61f768c)

📩 Контакты
Разработчик: @Dimash357
Email: katyorioblays@gmail.com


## 🛠️ Установка локально
```bash
git clone https://github.com/Dimash357/Visions-production.git
cd Visions-production

# Рекомендуется использовать Docker:
docker-compose up --build
