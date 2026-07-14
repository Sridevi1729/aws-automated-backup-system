import boto3
import datetime

# --- CONFIGURATION ---
RETENTION_DAYS = 7  # Keep backups for 7 days
TAG_KEY = 'Backup'
TAG_VALUE = 'true'

# Initialize the EC2 client
ec2 = boto3.client('ec2')

def lambda_handler(event, context):
    print("--- STARTING AUTOMATED EBS BACKUP PROCESS ---")
    
    # ==========================================
    # STEP 1: LOCATE TARGET VOLUMES
    # ==========================================
    try:
        volumes = ec2.describe_volumes(
            Filters=[
                {
                    'Name': f'tag:{TAG_KEY}', 
                    'Values': [TAG_VALUE]
                }
            ]
        )['Volumes']
    except Exception as e:
        print(f"Error describing volumes: {str(e)}")
        raise e
        
    print(f"Discovered {len(volumes)} volume(s) marked for backup.")
    
    created_snapshots = []
    
    # ==========================================
    # STEP 2: CREATE SNAPSHOTS
    # ==========================================
    for volume in volumes:
        vol_id = volume['VolumeId']
        today_str = datetime.date.today().strftime('%Y-%m-%d')
        description = f"Auto-backup for {vol_id} on {today_str}"
        
        try:
            # Create the snapshot
            snapshot = ec2.create_snapshot(
                VolumeId=vol_id,
                Description=description
            )
            snap_id = snapshot['SnapshotId']
            created_snapshots.append(snap_id)
            print(f"Successfully created snapshot: {snap_id} for volume: {vol_id}")
            
            # Tag the snapshot so we can track and manage it later
            ec2.create_tags(
                Resources=[snap_id],
                Tags=[
                    {'Key': 'CreatedBy', 'Value': 'AutomatedBackupLambda'},
                    {'Key': 'VolumeId', 'Value': vol_id}
                ]
            )
        except Exception as e:
            print(f"Error creating snapshot for volume {vol_id}: {str(e)}")
            continue

    # ==========================================
    # STEP 3: DELETE EXPIRED SNAPSHOTS (RETENTION)
    # ==========================================
    print("Scanning for expired snapshots...")
    try:
        # Only look for snapshots tagged as created by this tool to avoid deleting manual backups
        snapshots = ec2.describe_snapshots(
            Filters=[
                {
                    'Name': 'tag:CreatedBy', 
                    'Values': ['AutomatedBackupLambda']
                }
            ]
        )['Snapshots']
    except Exception as e:
        print(f"Error fetching snapshots: {str(e)}")
        snapshots = []

    now = datetime.datetime.now(datetime.timezone.utc)
    deleted_count = 0
    
    for snap in snapshots:
        start_time = snap['StartTime']
        # Calculate the age of the snapshot in days
        age = (now - start_time).days
        
        if age > RETENTION_DAYS:
            snap_id = snap['SnapshotId']
            print(f"Snapshot {snap_id} is {age} days old (exceeds limit of {RETENTION_DAYS} days). Deleting...")
            try:
                ec2.delete_snapshot(SnapshotId=snap_id)
                deleted_count += 1
            except Exception as e:
                print(f"Failed to delete snapshot {snap_id}: {str(e)}")
                
    print("--- AUTOMATED BACKUP PROCESS COMPLETED ---")
    
    return {
        'statusCode': 200,
        'body': {
            'message': 'Backup job completed successfully.',
            'snapshots_created': len(created_snapshots),
            'snapshots_deleted': deleted_count
        }
    }
