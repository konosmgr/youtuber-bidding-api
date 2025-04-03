# Youtuber Bidding API - Project State

## Project Structure
The Youtuber Bidding API is a Django-based backend for an auction platform specifically designed for YouTuber merchandise and memorabilia. The API provides endpoints for user authentication, item management, bidding, messaging, and admin functionalities.

### Main Components:
- **auctions**: Main Django app containing all business logic
- **core**: Project configuration and settings
- **Environments**: Development, Production settings separation

### Database:
- PostgreSQL is used for all environments
- Migrations are handled through Django's migration system
- Schema includes tables for users, items, bids, categories, messages, etc.

## Recent Changes

### 2025-04-02: Fixed Production Import Error
- Added compatibility module `debug_views.py` to fix production import error
- Updated `auctions/views/__init__.py` to ensure backward compatibility
- The error was due to a reference to a development-only module in production code

## Development Notes
- Local environment uses Django's debug features
- Production environment has DEBUG=False and additional security measures
- The database schema is consistent between environments
- All changes to the database should be performed through migrations

## Deployment Process
- Code is containerized using Docker
- Production deployment uses gunicorn for serving the application
- Environment-specific settings are loaded based on DJANGO_SETTINGS_MODULE

## Known Issues
- Production environment had an import error for `debug_views` which has been fixed by adding a compatibility module 