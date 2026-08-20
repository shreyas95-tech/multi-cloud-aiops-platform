# Deploy Multi-Cloud AIOps Platform to AWS EC2 (India - Mumbai)
# Run this from PowerShell: .\deploy-aws.ps1

$aws = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"
$KEY_NAME = "aiops-key"
$REGION = "ap-south-1"

Write-Host "=== Deploying Multi-Cloud AIOps Platform to AWS (Mumbai) ===" -ForegroundColor Cyan

# Step 1: Create or get security group
Write-Host "`n[1/6] Creating security group..." -ForegroundColor Yellow
$sgOutput = & $aws ec2 create-security-group --group-name aiops-sg --description "AIOps Platform" --region $REGION 2>&1
if ($sgOutput -match "GroupId") {
    $SG_ID = ($sgOutput | ConvertFrom-Json).GroupId
} else {
    # Already exists, look it up
    $SG_ID = & $aws ec2 describe-security-groups --group-names aiops-sg --region $REGION --query "SecurityGroups[0].GroupId" --output text
}
Write-Host "  Security Group: $SG_ID" -ForegroundColor Green

# Step 2: Add security group rules
Write-Host "`n[2/6] Configuring firewall rules..." -ForegroundColor Yellow
& $aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 22 --cidr 0.0.0.0/0 --region $REGION 2>$null
& $aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 80 --cidr 0.0.0.0/0 --region $REGION 2>$null
& $aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 8000 --cidr 0.0.0.0/0 --region $REGION 2>$null
Write-Host "  Rules configured (SSH:22, HTTP:80, API:8000)" -ForegroundColor Green

# Step 3: Create key pair (if not exists)
Write-Host "`n[3/6] Creating key pair..." -ForegroundColor Yellow
$keyOutput = & $aws ec2 create-key-pair --key-name $KEY_NAME --query "KeyMaterial" --output text --region $REGION 2>&1
if ($keyOutput -match "BEGIN") {
    $keyOutput | Out-File -FilePath "C:\Users\HP\aiops-key.pem" -Encoding ascii
    Write-Host "  Key saved to C:\Users\HP\aiops-key.pem" -ForegroundColor Green
} else {
    Write-Host "  Key pair already exists (using existing)" -ForegroundColor Green
}

# Step 4: Get the latest Ubuntu 22.04 AMI for ap-south-1
Write-Host "`n[4/6] Finding Ubuntu 22.04 AMI..." -ForegroundColor Yellow
$AMI_ID = & $aws ec2 describe-images --region $REGION --owners 099720109477 --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" "Name=state,Values=available" --query "sort_by(Images, &CreationDate)[-1].ImageId" --output text
Write-Host "  AMI: $AMI_ID" -ForegroundColor Green

# Step 5: Create user-data script
$USER_DATA = @'
#!/bin/bash
set -e
exec > /var/log/aiops-deploy.log 2>&1

# Install Docker and nginx
apt-get update
apt-get install -y docker.io nginx git
systemctl start docker
systemctl enable docker

# Clone the repo
cd /opt
git clone https://github.com/shreyas95-tech/multi-cloud-aiops-platform.git aiops
cd aiops

# Build and run Docker container
docker build -t aiops-platform .
docker run -d --name aiops \
  -p 8000:8000 \
  -e JWT_SECRET_KEY="$(openssl rand -hex 32)" \
  -v /opt/aiops/uploads/kb:/app/uploads/kb \
  --restart unless-stopped \
  aiops-platform

# Fix frontend API_BASE to use relative paths
sed -i 's|http://localhost:8000/api|/api|g' /opt/aiops/frontend/aiops/auth.js
sed -i 's|http://localhost:8000/api|/api|g' /opt/aiops/frontend/aiops/dashboard.js
sed -i 's|http://localhost:8000/api|/api|g' /opt/aiops/frontend/aiops/app.js

# Configure nginx as reverse proxy
cat > /etc/nginx/sites-available/default <<'NGINX'
server {
    listen 80;
    server_name _;

    location / {
        root /opt/aiops/frontend/aiops;
        index login.html;
        try_files $uri $uri/ /login.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_http_version 1.1;
        client_max_body_size 11M;
    }
}
NGINX

nginx -t && systemctl restart nginx
echo "DEPLOYMENT COMPLETE" > /opt/aiops/deploy-status.txt
'@

$USER_DATA_B64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($USER_DATA))

# Step 6: Launch EC2 instance
Write-Host "`n[5/6] Launching EC2 instance (t3.micro)..." -ForegroundColor Yellow
$INSTANCE_ID = & $aws ec2 run-instances --region $REGION --image-id $AMI_ID --instance-type t3.micro --key-name $KEY_NAME --security-group-ids $SG_ID --user-data $USER_DATA_B64 --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=AIOps-Platform}]" --query "Instances[0].InstanceId" --output text
Write-Host "  Instance ID: $INSTANCE_ID" -ForegroundColor Green

# Wait for instance
Write-Host "`n[6/6] Waiting for instance to start..." -ForegroundColor Yellow
& $aws ec2 wait instance-running --instance-ids $INSTANCE_ID --region $REGION
$PUBLIC_IP = & $aws ec2 describe-instances --instance-ids $INSTANCE_ID --region $REGION --query "Reservations[0].Instances[0].PublicIpAddress" --output text
Write-Host "  Instance running! IP: $PUBLIC_IP" -ForegroundColor Green

# Summary
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  DEPLOYMENT COMPLETE!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Platform URL:  http://$PUBLIC_IP/login.html" -ForegroundColor White
Write-Host "  Login:         admin / Admin@1234" -ForegroundColor White
Write-Host "  Region:        ap-south-1 (Mumbai, India)" -ForegroundColor White
Write-Host ""
Write-Host "  Wait 3-4 minutes for Docker build to finish." -ForegroundColor Yellow
Write-Host "  If page doesn't load, wait and refresh." -ForegroundColor Yellow
Write-Host ""
Write-Host "  SSH: ssh -i C:\Users\HP\aiops-key.pem ubuntu@$PUBLIC_IP" -ForegroundColor White
Write-Host ""
