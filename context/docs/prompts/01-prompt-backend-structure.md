# Project Launchpad - Backend Planning and configurations

This is a web applicaton project directory. Before we start coding, business logic,
application logic let's first plan the project's stack, directory structure,
database selection & configuration.

I've selected the frontend & backend framework for this web application.
This project will have seperate backend and frontend directory following
the modular monolithic project structure in this root directory.

INITIAL PROJECT BRIEF:

- `@context/docs/plans/01-client-brief.md`

TECHNICAL REQUIREMENTS:

- FastAPI/Python 3.10.12
- Postgres DB
- Redis for Cache
- JWT Authentication
- Background Tasks
- Pydantic
- Alembic

CONTEXT:

For backend I've chosen FastAPI which is a python framework for the backend. I want
specifically to use python 3.10.12 version and pip for installing
python packages to the environment.

I've learned FastAPI from Corey Shafer's FastAPI playlist. I loved the way he structured
the project. In his project he has done both the backend and frontend with this framework.
But we'll have the frontend framework setup later. I've taken important notes on all the
videos available in the playlist.

- Notes - `@context/docs/fastapi/`

From that I want you to learn the coding style, project setup, directory setup and
whatever we need to setup for the backend for production level configuration. Remember we
don't want to use docker for this project. I want to have dev and prod environments handled
in this project.

I'll later design the database schema. Don't need to think of the db tables/models or
anything as it is only to initiate the project's structure and environment. But for the
structure you can create some dummy/empty files to accomodate the initial project directory.

After all the learning, you have to create a few markdown files for me. You need to create a
coding-standards.md, project-overview.md file. For doing this please follow the structure given
in the references beneath. And also I want you to create another markdown file which can be
used as a context of a complete project maintainence, coding strucuture and directory for
this project and also in the future FastAPI projects on a high level abstract level with a
senior engineer perspective. Create the files in the `@context` directory.

- conding standard file example - `@context/docs/reference/coding-standards-example.md`
- project overview file example - `@context/docs/reference/project-overview-example.md`

These references are of a different project. So just follow the structure. Not the contents.

And also based on the findings please suggest me things that you feel have missed out to mention
here.

The directory (frontend) for the frontend app will be discussed and worked on later.
