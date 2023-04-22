import json
import redis
import os
from dotenv import load_dotenv
from datetime import datetime, timezone
import mysql.connector

def isoformat_js(dt: datetime):
    return (
        dt.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
)

load_dotenv()

m = mysql.connector.connect(
    ssl_disabled=False,
    host=os.getenv("MYSQL_HOST"),
    port=os.getenv("MYSQL_PORT"),
    database=os.getenv("MYSQL_DATABASE"),
    user=os.getenv("MYSQL_USERNAME"),
    password=os.getenv("MYSQL_PASSWORD"),
)

r = redis.Redis(
  host=os.getenv("REDIS_HOST"),
  port=os.getenv("REDIS_PORT"),
  password=os.getenv("REDIS_PASSWORD"),
  ssl=os.getenv("REDIS_SSL"),
  decode_responses=True
)

user_prefix = os.getenv("UPSTASH_USER_PREFIX")
session_prefix = os.getenv("UPSTASH_SESSION_PREFIX")

print(f"User prefix set to: \"{user_prefix}\"", f"\nSession prefix set to: \"{session_prefix}\"", sep = ", ")

# Check if user_prefix and session_prefix are set
if not user_prefix:
    print("User prefix not set.")
    exit()
if not session_prefix:
    print("Session prefix not set.")
    exit()

# Check if connection to PlanetScale and Upstash is successful
if not m.is_connected():
    print("Mysql not connected.")
    exit()
    
if not r.ping():
    print("Redis not connected.")
    exit()

headless = os.getenv("HEADLESS")
if not headless:
    prompt_answer = input("Established connection to PlanetScale and Upstash. Do you want to start the migration?\n(y/n):")
    if not prompt_answer.lower() in ["y","yes"]:
        print("Migration cancelled.")
        exit()
    else:
        print("Starting migration...")

cursor = m.cursor(dictionary=True)

# USERS
cursor.execute("select * from users")
users = cursor.fetchall()
for user in users:
    user_id = user['id']
    email = user['email']
    email_verified = isoformat_js(user['email_verified'])
    registered = bool(user['registered'])
    display_name = user['display_name']
    
    # Get users existing access tokens (if any)
    cursor.execute(f'select service, token from access_tokens where user_id = "{user_id}"')
    access_tokens = cursor.fetchall()
    directus_token = None
    pterodactyl_token = None
    whmcs_token = None
    for access_token in access_tokens:
        if (access_token['service'] == 'directus'):
            directus_token = access_token['token']
        if (access_token['service'] == 'pterodactyl'):
            pterodactyl_token = access_token['token']
        if (access_token['service'] == 'whmcs'):
            whmcs_token = access_token['token']
            
    # Check if user already exists
    existing_user_id_key = user_prefix + user_id
    existing_user_found = r.get(existing_user_id_key)
    if existing_user_found:
        # Update existing user object
        user_data = json.loads(existing_user_found)
        if not user_data['email']:
            user_data['email'] = email
        if not user_data['emailVerified']:
            user_data['emailVerified'] = email_verified
        if not user_data['displayName']:
            user_data['displayName'] = display_name
        if not user_data['registered'] == True:
            user_data['registered'] = registered    
        
        # Add tokens from old db if they dont exist in the new one
        existing_access_tokens = user_data['accessTokens']
        
        if 'directus' in existing_access_tokens and not existing_access_tokens['directus'] and directus_token:
            existing_access_tokens['directus'] = directus_token
        if 'pterodactyl' in existing_access_tokens and not existing_access_tokens['pterodactyl'] and pterodactyl_token:
            existing_access_tokens['pterodactyl'] = pterodactyl_token
        if 'whmcs' in existing_access_tokens and not existing_access_tokens['whmcs'] and whmcs_token:
            existing_access_tokens['whmcs'] = whmcs_token

        user_data['accessTokens'] = existing_access_tokens
        
        print("Updating existing user: ", user_id, "\nto: ", user_data, "\n", sep = "")

    else:
        # Build new user object
        user_data = {
            "email": email,
            "emailVerified": email_verified,
            "id": user_id, 
            "displayName": display_name, 
            "registered": registered, 
            }
        
        if access_tokens:
            users_access_tokens = {
                "directus": directus_token,
                "pterodactyl": pterodactyl_token,
                "whmcs": whmcs_token
            }
            user_data['accessTokens'] = users_access_tokens
        else:
            user_data['accessTokens'] = {}
        
        print("Creating new user: ", user_id, "\nwith: ", user_data, "\n", sep = "")
        
    # Transfer users existing sessions (if any)
    cursor.execute(f'select * from sessions where userId = "{user_id}"')
    sessions = cursor.fetchall()

    if sessions:
        latestSession = None
        for session in sessions:
            session_token = session['sessionToken']

            if latestSession == None:
                latestSession = session
            
            if session['expires'] > latestSession['expires']:
                latestSession = session
            session_expires = isoformat_js(session['expires'])
            session_data = {"sessionToken": session_token, "userId": user_id, "expires": session_expires}
            stringified_session = json.dumps(session_data, separators=(',', ':'), default=str)
            
            # Set auth object
            r.set(session_prefix + session_token, stringified_session)
        
        # Set user session lookup key
        user_session_key = session_prefix + 'by-user-id:' + user_id
        r.set(user_session_key, session_prefix + latestSession['sessionToken'])

    # Set user object
    stringified_user = json.dumps(user_data, separators=(',', ':'), default=str)
    r.set(existing_user_id_key, stringified_user)
    
    # Set user lookup keys
    user_email_key = user_prefix + "email:" + user_data['email']
    r.set(user_email_key, user_id)

    if (user_data['displayName']):
        user_display_name_key = user_prefix + "display-name:" + user_data['displayName']
        r.set(user_display_name_key, user_id)
        
print("All users have been migrated.")