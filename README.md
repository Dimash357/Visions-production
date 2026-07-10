# Visions

A web platform for managing educational tasks, tracking student progress, and simplifying communication between teachers and students.

## Features

* User authentication and authorization
* Student and teacher accounts
* Task creation and management
* Homework submission
* File upload support
* Personal user profiles
* Progress tracking
* Admin panel for project management
* Responsive interface

## Technologies

* Python
* Django
* HTML5
* CSS3
* JavaScript
* PostgreSQL
* Git
* Docker

## Project Structure

```
Visions/
├── django_app/
├── django_settings/
├── templates/
├── static/
├── static_external/
├── media/
├── docker-compose.yml/
├── Dockerfile/
├── manage.py
├── requirements.txt
└── README.md
```

## Installation

Clone the repository:

```bash
git clone https://github.com/Dimash357/Visions-production.git
cd Visions-production
```

Create a virtual environment:

```bash
python -m venv venv
```

Activate it.

Windows:

```bash
venv\Scripts\activate
```

Linux / macOS:

```bash
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run migrations:

```bash
python manage.py migrate
```

Start the development server:

```bash
python manage.py runserver
```

Open your browser:

```
http://127.0.0.1:8000/
```

## Future Improvements

* Email notifications
* REST API
* Docker support
* PostgreSQL deployment
* Real-time notifications
* Improved dashboard analytics
* Dark mode

## License

This project is intended for educational and portfolio purposes.

## Author

**Dimash Sarsen**

GitHub: https://github.com/Dimash357
