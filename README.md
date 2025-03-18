# AWS Connect to Adobe Experience Platform Event Forwarder

This Lambda function forwards events from AWS Connect to Adobe Experience Platform using environment variables instead of AWS Secrets Manager.

## Prerequisites

- Python 3.9+
- AWS CLI
- AWS SAM CLI
- Docker (for local testing)
- VS Code with AWS Toolkit extension
- Adobe Experience Platform credentials

## Implementation Steps

### 1. Set Up Project Files

Create the following project structure:
```
connect-aep-forwarder/
├── app.py              # Lambda function code
├── template.yaml       # SAM template
├── samconfig.toml      # SAM configuration
├── requirements.txt    # Dependencies
├── .env.sample         # Template for environment variables
└── env.json            # SAM local environment config
```

### 2. Create Requirements File

Create `requirements.txt`:
```
boto3>=1.28.0
requests>=2.31.0
python-dotenv>=1.0.0
```

### 3. Set Up Local Environment Variables

Create `.env.sample` and `.env` files:
```
AEP_ENDPOINT=https://dcs.adobedc.net/collection/your-collection-id
IMS_ENDPOINT=https://ims-na1.adobelogin.com/ims/token/v2
CLIENT_ID=your-client-id
CLIENT_SECRET=your-client-secret
IMS_ORG=your-org-id@AdobeOrg
TECHNICAL_ACCOUNT_ID=your-technical-account-id
SCOPES=openid,AdobeID,read_organizations,additional_info.projectedProductContext,session
FLOW_ID=your-flow-id
SANDBOX_NAME=your-sandbox-name
```

### 4. Create SAM Environment Config

Create `env.json`:
```json
{
  "AEPConnectFunction": {
    "AEP_ENDPOINT": "https://dcs.adobedc.net/collection/your-collection-id",
    "IMS_ENDPOINT": "https://ims-na1.adobelogin.com/ims/token/v2",
    "CLIENT_ID": "your-client-id",
    "CLIENT_SECRET": "your-client-secret",
    "IMS_ORG": "your-org-id@AdobeOrg",
    "TECHNICAL_ACCOUNT_ID": "your-technical-account-id",
    "SCOPES": "openid,AdobeID,read_organizations,additional_info.projectedProductContext,session",
    "FLOW_ID": "your-flow-id",
    "SANDBOX_NAME": "your-sandbox-name"
  }
}
```

## Local Testing

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Build and run locally:
   ```bash
   sam build
   sam local start-api --env-vars env.json
   ```

3. Test with a sample POST request to http://127.0.0.1:3000/connect-event:
   ```json
   {
     "order_id": "XU7L020O9M59VQ4S98",
     "order_time": "2023-08-05T06:23:23Z",
     "order_total": "69.69",
     "customer_id": "64a85c39fc13ae36aebeed8c",
     "customer_email": "customer@example.com",
     "customer_name": "John Doe"
   }
   ```

## Production Deployment

1. Store credentials in AWS Systems Manager Parameter Store:
   ```bash
   aws ssm put-parameter --name "/aep-connect/AepEndpoint" --value "https://dcs.adobedc.net/collection/your-collection-id" --type "SecureString"
   aws ssm put-parameter --name "/aep-connect/ClientId" --value "your-client-id" --type "SecureString"
   aws ssm put-parameter --name "/aep-connect/ClientSecret" --value "your-client-secret" --type "SecureString"
   aws ssm put-parameter --name "/aep-connect/ImsOrg" --value "your-org-id@AdobeOrg" --type "SecureString"
   aws ssm put-parameter --name "/aep-connect/FlowId" --value "your-flow-id" --type "SecureString"
   aws ssm put-parameter --name "/aep-connect/SandboxName" --value "your-sandbox-name" --type "SecureString"
   ```

2. Deploy using VS Code AWS Toolkit:
   - Open Command Palette (Ctrl+Shift+P or Cmd+Shift+P)
   - Select "AWS: Deploy SAM Application"
   - Choose template.yaml
   - Select deployment parameters
   - Wait for deployment to complete

3. Alternatively, deploy with SAM CLI:
   ```bash
   sam deploy --guided
   ```

## Troubleshooting

- **Docker issues**: Ensure Docker is running before starting local testing
- **Deployment failures**: Check IAM permissions and CloudFormation logs
- **ROLLBACK_COMPLETE state**: Delete the stack before redeploying:
  ```bash
  aws cloudformation delete-stack --stack-name your-stack-name
  ```
- **Token errors**: Verify your Adobe credentials are correct

## Required IAM Permissions

Ensure your AWS user has these permissions:
- iam:CreateRole, iam:AttachRolePolicy, iam:PassRole
- cloudformation:CreateStack, cloudformation:CreateChangeSet
- lambda:CreateFunction, lambda:AddPermission
- apigateway:POST, apigateway:PUT, apigateway:GET
- s3:CreateBucket, s3:PutObject
- ssm:PutParameter, ssm:GetParameter*