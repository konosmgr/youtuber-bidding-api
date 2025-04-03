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

### 2025-04-03: Fixed API Routing Architecture
- Identified and resolved major API routing issue between development and production environments
- Added path-based routing to match development configuration
- Resolved conflicts between frontend routes and backend API endpoints

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

## Architecture Explanation: API Routing Problem

### Original Problem
The project experienced a significant architectural inconsistency between development and production environments:

1. **Development Environment:**
   - Frontend and backend both running on the same domain
   - API accessed through path-based routing (`/api/*` endpoints)
   - SvelteKit dev server proxied requests to the Django backend

2. **Production Environment:**
   - Initially configured with subdomain-based API routing (`api.konosmgr.com`)
   - Frontend code still constructed URLs assuming path-based routing
   - Created URL mismatches like `api.konosmgr.com/api/*` (double `/api` prefix)
   - Frontend requests failed with 404 errors

### Complicating Factors
1. **Frontend Route Conflicts:**
   - SvelteKit frontend had its own `/api` routes under `src/routes/api/*`
   - These frontend routes intercepted some API requests before they reached the backend
   - Created confusion between frontend and backend API endpoints

2. **Cross-Domain Issues:**
   - Subdomain architecture required complex CORS configuration
   - Cookie handling across domains complicated authentication
   - CSRF protection more difficult to implement correctly

### Implemented Solution
1. **Unified Domain Architecture:**
   - Configured Traefik to route `/api/*` paths on main domain to backend service
   - Maintained backwards compatibility with existing subdomain
   - Simplified frontend environment variables to use relative paths

2. **Frontend Adjustments:**
   - Updated API client code to handle relative URLs properly
   - Ensured consistent path construction throughout the application
   - Renamed conflicting frontend routes to avoid interception

3. **Infrastructure Updates:**
   - Added new routing rules in Traefik configuration
   - Maintained subdomain for gradual migration

### Benefits of the Solution
1. **Consistency:** Development and production now use the same API URL structure
2. **Simplicity:** Removed cross-domain complexities
3. **Reliability:** Eliminated URL construction issues
4. **Maintainability:** Simplified architecture is easier to debug and extend

This architectural change aligns with modern web application best practices, where APIs are typically served from the same domain as the frontend using path-based routing. 