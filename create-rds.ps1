# Create RDS PostgreSQL instance (Free Tier) for AIOps Platform
$aws = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"
$REGION = "ap-south-1"

Write-Host "=== Creating RDS PostgreSQL (Free Tier) ===" -ForegroundColor Cyan

# Step 1: Get the security group ID for aiops-sg in ap-south-1
Write-Host "`n[1/4] Finding security group..." -ForegroundColor Yellow
$SG_ID = & $aws ec2 describe-security-groups --filters "Name=group-name,Values=aiops-sg" --query "SecurityGroups[0].GroupId" --output text --region $REGION
Write-Host "  Security Group: $SG_ID" -ForegroundColor Green

# Step 2: Add PostgreSQL inbound rule (5432)
Write-Host "`n[2/4] Adding PostgreSQL rule to security group..." -ForegroundColor Yellow
& $aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 5432 --cidr 0.0.0.0/0 --region $REGION 2>$null
Write-Host "  PostgreSQL rule added" -ForegroundColor Green

# Step 3: Create RDS instance
Write-Host "`n[3/4] Creating RDS instance (this takes 3-5 minutes)..." -ForegroundColor Yellow
& $aws rds create-db-instance --db-instance-identifier aiops-db --db-instance-class db.t3.micro --engine postgres --master-username aiopsadmin --master-user-password "AiOps2024Secure!" --allocated-storage 20 --publicly-accessible --backup-retention-period 0 --no-multi-az --storage-type gp2 --vpc-security-group-ids $SG_ID --db-name aiopsplatform --region $REGION --query "DBInstance.[DBInstanceIdentifier,DBInstanceStatus]" --output text
Write-Host "  RDS instance creating..." -ForegroundColor Green

# Step 4: Wait for it to be available
Write-Host "`n[4/4] Waiting for RDS to become available (3-5 minutes)..." -ForegroundColor Yellow
& $aws rds wait db-instance-available --db-instance-identifier aiops-db --region $REGION
$ENDPOINT = & $aws rds describe-db-instances --db-instance-identifier aiops-db --region $REGION --query "DBInstances[0].Endpoint.Address" --output text
Write-Host "  RDS is ready!" -ForegroundColor Green

# Summary
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  RDS POSTGRESQL CREATED!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Endpoint: $ENDPOINT" -ForegroundColor White
Write-Host "  Database: aiopsplatform" -ForegroundColor White
Write-Host "  Username: aiopsadmin" -ForegroundColor White
Write-Host "  Password: AiOps2024Secure!" -ForegroundColor White
Write-Host "  Region:   ap-south-1" -ForegroundColor White
Write-Host ""
Write-Host "  Connection string:" -ForegroundColor White
Write-Host "  postgresql://aiopsadmin:AiOps2024Secure!@${ENDPOINT}:5432/aiopsplatform" -ForegroundColor Cyan
Write-Host ""
