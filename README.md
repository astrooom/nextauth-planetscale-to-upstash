# nextauth-planetscale-to-upstash
Python 3 Script to migrate NextAuth users and sessions from PlanetScale to Upstash.

## Usage
1. Set appropriate values in a `.env` in the same folder as the script runs in. Check `.env.sample` for all values to be set.
2. Install required dependencies (mysql-connector and redis) using ```pip install -r requirements.txt```
3. Run the script using ```python(3) run.py```. You will be prompted before the migration starts unless you set `HEADLESS=true` in the .env

## Notes
This migration script is designed to work with a separate table for `auth_tokens`, specifically to migrate tokens for [Directus](https://github.com/directus/directus), [Pterodactyl Panel](https://github.com/pterodactyl/panel) and [WHMCS](https://www.whmcs.com/) by default. Please change or remove this code depending on how your setup looks.