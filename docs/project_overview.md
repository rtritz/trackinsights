
# Project Structure

See the root `CLAUDE.md` for the authoritative, up-to-date project structure
(the `common/` shared library, `web/` Flask app layout, and `standalone/`
data-pipeline programs) -- kept here only once to avoid this document
drifting out of sync with it again.

# Project Roles and Workflow Overview

## Frontend Developer

The frontend developer is responsible for creating the user interface that students and users will see and interact with. This includes building HTML templates, styling them with TailwindCSS, and adding interactivity using JavaScript. The frontend connects to the backend by displaying data provided through Flask templates or by fetching data from API endpoints. The frontend developer should test the pages locally by running the Flask server and ensure that the user interface updates correctly with real data. They should work closely with the backend developer to understand route names, data formats, and what information will be available on each page.

## Backend Developer

The backend developer handles the server-side logic of the application. This includes setting up the database, defining tables and models, writing queries to store and retrieve data, and creating routes and API endpoints for the frontend to access. The backend developer ensures that data is delivered accurately and efficiently, whether it’s rendered in templates or returned as JSON for dynamic updates. They should test each route and database query, and provide clear documentation or examples for the frontend developer so that the two sides can integrate smoothly.

## Collaboration

Both developers should clone the shared repository and work on separate branches for their roles. They need to frequently pull updates from the main branch and communicate about changes to routes, templates, and data formats. By following this workflow, the backend will reliably serve data, and the frontend will effectively display and interact with it, resulting in a complete, functioning web application.
