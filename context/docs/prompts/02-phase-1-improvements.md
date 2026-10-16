# Phase 1 Improvements

As we have completed the phase 1 there are some improvements that I would like to
make. Checkout to a new branch to make these improvments.

### General Improvements

- As we initially started calling an Account which has been renamed to Profile. The
  code seems to reflect that but in some documents in the @context directory it is
  still refered as Account. Update that please.

- The current backend directory structure is not present in the current
  @context/project-overview.md file. It shows the old directory structure. Need to
  update it.
- In the current backend structure we have service file for each module which is
  great. But each service file consists all the functions directly. I would like to
  change that. As an example in the users module there are User, Role, Profile,
  MemberFollow models. Each has their own business logic of create/read/update/delete
  operations. I would like to have these have their own services that could help their
  business logic. For that in the service file for the user module I would like to have
  seperate ServiceClass that would serve their business logic seperately. Kind of a OOP
  implementations in the service files. For example in user moduel's service:

```python

class UserService:
    def __init__(self, some_initiating_var):
        self.some_initiating_var = some_initiating_var

    def .....
    .........
    .........

class UserRoleService:
    def __init__(self, some_initiating_var):
        self.some_initiating_var = some_initiating_var

    def .....
    .........
    .........




class UserProfileService:
    def __init__(self, some_initiating_var):
        self.some_initiating_var = some_initiating_var

    def .....
    .........
    .........



class MemberFollowService:
    def __init__(self, some_initiating_var):
        self.some_initiating_var = some_initiating_var

    def .....
    .........
    .........

```

This structure in the whole application would help us to understand and manage the code
in a scalable way. I would like to implement this in all the services file of the modules
and also update the documentation under @context so that the project context always knows
about it.

- In the backend @backend/src/core/config.py file the class Settings raw inputs. Isn't it?
  Do you think we should update this to the beneath example ? Or is it already doing it in a
  dynamic way.

example

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=resolve_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Launchpad Backend"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = env.str('SECRET_KEY') # -> example
    database_url: str
    redis_url: str
    jwt_algorithm: str = "HS256"
    access_token_expire_min: int = 30
    refresh_token_expire_days: int = 7
    email_verification_expire_hours: int = 24
    password_reset_expire_hours: int = 1
    google_client_id: str | None = None
```

- Pydantic schemas in the schemas should have seperate schemas for Create/Update/Read schemas.

### Business Logic

Currently there isn't much of a form validation/validation in the backend. But to
make the application behave consistently we need to understand the business logic
as well to write the validations. And I think these validations should done under
pydantic schemas in the schema files for each modules.

Once the validations are done the services can create/update/delete/retrive according
to the business logic.

- As we only have the signup here and we already know the roles that we want, we want
  to seed the db table with the roles. You can provide me the seed sql that I would run
  through the psql in my DB that is locally connected to the project.
- Now while signup, there will be two signup options. User can signup as a founder or
  can signup as a member. According to that, the user and a profile will be created.
- The validation will validate if a user with this email/phone_number already exists.
  If the user has a member profile and the signup request is for a founder role
  then it should inform the user that you already have a member's profile and upon the
  users confirmation it will create a founder profile. This goes vice verca.
  Because based on the profile role the user's access and persmission or later business logic would be set.
- Other than member/founder no other role would have the signup option. So the validation
  should always validate for these two roles.

**_Important_**
_For all the changes we made if their is anything that we need to update in the @context
directory documents related to the project please do that_
