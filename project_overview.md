
# Project Structure

```
track_app/
│
├── app.py                  # Main entry point that starts the Flask server. Imports and initializes the app from backend/__init__.py.
├── config.py               # Stores configuration settings such as database path, debug mode, etc.
│
├── backend/                # Contains all Flask logic — routes, models, and database queries. Used by the back-end developer.
│   ├── __init__.py         # Initializes the Flask app, registers blueprints, and connects to the database.
│   ├── models.py           # Defines SQLAlchemy models (tables such as Athlete, School, etc.).
│   ├── queries.py          # Reusable database functions (e.g., get_athletes(), add_school()).
│   ├── routes/             # Organizes all Flask route files for modularity.
│   │   ├── __init__.py
│   │   ├── main_routes.py  # Routes that render web pages (e.g., /home, /search).
│   │   └── api_routes.py   # Routes that serve JSON responses for APIs or AJAX calls.
│
├── frontend/               # Contains all user-facing assets — HTML, Tailwind CSS, JS, and images. Used by the front-end developer.
│   ├── templates/          # Jinja2 HTML templates rendered by Flask.
│   │   ├── base.html
│   │   ├── home.html
│   │   ├── athlete-search.html
│   │   └── ...
│   ├── static/             # Static files served to the browser.
│   │   ├── css/
│   │   │   └── styles.css  # Tailwind build output file.
│   │   ├── js/
│   │   │   └── main.js     # Custom JavaScript for interactivity.
│   │   └── images/         # Project images and icons.
│   └── tailwind.config.js  # Tailwind configuration for custom colors, fonts, and themes.
│
├── data/                   # Storage of DB
│   └── Track.db            # SQLite database file.
│
├── tests/                  # Optional folder for test scripts to verify routes, APIs, and models.
│   └── test_routes.py
│
├── requirements.txt        # Lists Python dependencies for easy installation.
├── README.md               # Project documentation and setup instructions.
└── .gitignore              # Excludes unnecessary files (e.g., __pycache__, .env, Track.db).
```
# Project Roles and Workflow Overview

## Frontend Developer

The frontend developer is responsible for creating the user interface that students and users will see and interact with. This includes building HTML templates, styling them with TailwindCSS, and adding interactivity using JavaScript. The frontend connects to the backend by displaying data provided through Flask templates or by fetching data from API endpoints. The frontend developer should test the pages locally by running the Flask server and ensure that the user interface updates correctly with real data. They should work closely with the backend developer to understand route names, data formats, and what information will be available on each page.

## Backend Developer

The backend developer handles the server-side logic of the application. This includes setting up the database, defining tables and models, writing queries to store and retrieve data, and creating routes and API endpoints for the frontend to access. The backend developer ensures that data is delivered accurately and efficiently, whether it’s rendered in templates or returned as JSON for dynamic updates. They should test each route and database query, and provide clear documentation or examples for the frontend developer so that the two sides can integrate smoothly.

## Collaboration

Both developers should clone the shared repository and work on separate branches for their roles. They need to frequently pull updates from the main branch and communicate about changes to routes, templates, and data formats. By following this workflow, the backend will reliably serve data, and the frontend will effectively display and interact with it, resulting in a complete, functioning web application.
