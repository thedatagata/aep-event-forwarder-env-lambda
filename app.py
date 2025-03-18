import os
import json
import logging
import requests
from datetime import datetime, timedelta

# Load .env file for local development
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # In production, we don't need dotenv
    pass

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Token cache for development and production
_token_cache = {
    'access_token': None,
    'expiry': None
}

def get_aep_credentials():
    """
    Retrieve Adobe Experience Platform credentials from environment variables
    """
    logger.info("Retrieving credentials from environment variables")
    credentials = {
        "AEP_ENDPOINT": os.environ.get('AEP_ENDPOINT'),
        "IMS_ENDPOINT": os.environ.get('IMS_ENDPOINT', 'https://ims-na1.adobelogin.com/ims/token/v2'),
        "CLIENT_ID": os.environ.get('CLIENT_ID'),
        "CLIENT_SECRET": os.environ.get('CLIENT_SECRET'),
        "IMS_ORG": os.environ.get('IMS_ORG'),
        "TECHNICAL_ACCOUNT_ID": os.environ.get('TECHNICAL_ACCOUNT_ID'),
        "SCOPES": os.environ.get('SCOPES', 'openid,AdobeID,read_organizations,additional_info.projectedProductContext,session'),
        "FLOW_ID": os.environ.get('FLOW_ID'),
        "SANDBOX_NAME": os.environ.get('SANDBOX_NAME')
    }
    
    # Validate required credentials
    required_fields = ["AEP_ENDPOINT", "CLIENT_ID", "CLIENT_SECRET", "IMS_ORG", "FLOW_ID", "SANDBOX_NAME"]
    missing_fields = [field for field in required_fields if not credentials.get(field)]
    
    if missing_fields:
        logger.error(f"Missing required environment variables: {', '.join(missing_fields)}")
        raise ValueError(f"Missing required environment variables: {', '.join(missing_fields)}")
    
    return credentials

def get_access_token(force_refresh=False):
    """
    Retrieve a valid access token from cache or generate a new one if needed
    
    Args:
        force_refresh (bool): If True, force generate a new token regardless of expiry
    """
    global _token_cache
    
    if not force_refresh and _token_cache['access_token'] and _token_cache['expiry']:
        # Check if token is still valid (with 5-minute buffer)
        if datetime.now() < _token_cache['expiry'] - timedelta(minutes=5):
            logger.info("Using existing token from memory cache")
            return _token_cache['access_token']
    
    logger.info("Token expired or not found, generating new token")
    
    # Generate new token
    new_token, expires_in = generate_new_token()
    
    # Update cache
    _token_cache['access_token'] = new_token
    _token_cache['expiry'] = datetime.now() + timedelta(seconds=expires_in)
    
    return new_token

def generate_new_token():
    """
    Generate a new access token from Adobe IMS
    
    Returns:
        tuple: (access_token, expires_in)
    """
    logger.info("Generating new Adobe access token")
    
    # Get credentials
    credentials = get_aep_credentials()
    
    data = {
        "grant_type": "client_credentials",
        "client_id": credentials.get("CLIENT_ID"),
        "client_secret": credentials.get("CLIENT_SECRET"),
        "scope": credentials.get("SCOPES")
    }
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    try:
        response = requests.post(
            credentials.get("IMS_ENDPOINT"),
            headers=headers,
            data=data,
            timeout=10.0
        )
        
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data.get('access_token')
        expires_in = token_data.get('expires_in', 86400)  # Default to 24 hours if not provided
        
        return access_token, expires_in
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Error generating token: {str(e)}")
        if hasattr(e, 'response') and e.response:
            logger.error(f"Response: {e.response.text}")
        raise

def send_to_aep(event_data, access_token, retry_attempt=0):
    """
    Send event data to Adobe Experience Platform
    
    Args:
        event_data: The event data to send to AEP
        access_token: The Adobe access token to use for authentication
        retry_attempt: Internal counter to prevent infinite retry loops
    """
    # Get credentials
    credentials = get_aep_credentials()
    
    aep_endpoint = credentials.get("AEP_ENDPOINT") 
    flow_id = credentials.get("FLOW_ID")
    sandbox_name = credentials.get("SANDBOX_NAME") 

    url = aep_endpoint
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {access_token}',
        'x-adobe-flow-id': flow_id,
        'x-sandbox-name': sandbox_name
    }
    
    logger.info(f"Sending data to AEP URL: {url}")
    
    try:
        response = requests.post(url, json=event_data, headers=headers)
        
        # Handle 401 errors which may indicate an expired token
        if response.status_code == 401 and retry_attempt == 0:
            try:
                error_data = response.json()
                error_type = error_data.get("type", "")
                error_title = error_data.get("title", "")
                
                # Check if this is a token expiration error
                if ("token expired" in error_title.lower() or 
                    "authorization token expired" in error_title.lower() or
                    "EXEG-0503-401" in error_type):
                    
                    logger.info("Access token expired. Generating a new token and retrying.")
                    
                    # Force generate a new token
                    new_token = get_access_token(force_refresh=True)
                    
                    # Retry the request with the new token (only retry once to avoid infinite loops)
                    return send_to_aep(event_data, new_token, retry_attempt=1)
            except (ValueError, KeyError, json.JSONDecodeError) as e:
                logger.error(f"Error parsing 401 response: {str(e)}")
                # Continue with normal error handling if we can't parse the response
        
        # For all other cases, proceed as normal
        response.raise_for_status()
        logger.info(f"Successfully sent event to AEP: {response.status_code}")
        
        try:
            return response.json()
        except json.JSONDecodeError:
            logger.info("Response was not JSON, returning text")
            return {"responseText": response.text}
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending to AEP: {str(e)}")
        if hasattr(e, 'response') and e.response:
            logger.error(f"Response status: {e.response.status_code}")
            logger.error(f"Response body: {e.response.text}")
        raise

def lambda_handler(event, context):
    """
    Lambda handler for processing events and forwarding to AEP
    """
    logger.info("Received event")
    
    try:
        # Handle API Gateway events
        if isinstance(event, dict) and 'body' in event:
            try:
                if event['body']:
                    # If body is a string (which it should be from API Gateway), parse it
                    if isinstance(event['body'], str):
                        event = json.loads(event['body'])
                    else:
                        event = event['body']
            except json.JSONDecodeError as e:
                logger.error(f"Could not parse event body as JSON: {str(e)}")
                return {
                    'statusCode': 400,
                    'body': json.dumps({'message': 'Invalid JSON in request body'})
                }
        
        # Get access token
        try:
            access_token = get_access_token()
        except Exception as e:
            logger.error(f"Failed to get access token: {str(e)}")
            return {
                'statusCode': 500,
                'body': json.dumps({'message': 'Failed to authenticate with Adobe API'})
            }
        
        # Send event to AEP
        try:
            aep_response = send_to_aep(event, access_token)
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Event successfully forwarded to AEP',
                    'aepResponse': aep_response
                })
            }
        except Exception as e:
            logger.error(f"Failed to send event to AEP: {str(e)}")
            return {
                'statusCode': 502,
                'body': json.dumps({'message': 'Failed to send event to Adobe Experience Platform'})
            }
    
    except Exception as e:
        logger.error(f"Error processing event: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'message': f'Error processing event: {str(e)}'})
        }