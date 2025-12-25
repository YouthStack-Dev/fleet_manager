#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Production Deployment Script for Fleet Manager Database Migrations
Run this script to safely deploy migrations to production

Usage:
    python deploy_prod.py --help
    python deploy_prod.py --backup
    python deploy_prod.py --deploy
    python deploy_prod.py --verify
    python deploy_prod.py --rollback
"""

import sys
import os
import subprocess
import argparse
from datetime import datetime
from pathlib import Path

# Fix Windows Unicode encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class ProductionDeployer:
    """Handle production deployment of database migrations."""
    
    def __init__(self, env_file=None):
        """Initialize deployer with optional environment file."""
        self.env_file = env_file
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.backup_dir = project_root / "backups"
        self.backup_dir.mkdir(exist_ok=True)
        
        # Load environment
        self.load_environment()
    
    def load_environment(self):
        """Load environment variables."""
        if self.env_file and Path(self.env_file).exists():
            from dotenv import load_dotenv
            load_dotenv(self.env_file)
        
        from app.config import settings
        self.settings = settings
    
    def print_header(self, title):
        """Print formatted header."""
        print(f"\n{'='*70}")
        print(f"  {title}")
        print(f"{'='*70}\n")
    
    def print_step(self, step_num, title):
        """Print formatted step."""
        print(f"Step {step_num}: {title}")
        print(f"{'-'*65}")
    
    def run_command(self, command, description, critical=True):
        """Run command and return success status."""
        print(f"Running: {description}...")
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
        )
        
        if result.returncode != 0:
            print(f"FAILED: {result.stderr}")
            if critical:
                print(f"\nDeployment aborted due to critical failure!")
                sys.exit(1)
            return False
        
        print(f"Success: {description}")
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                if line:
                    print(f"   {line}")
        
        return True
    
    def backup_database(self, docker=False):
        """Backup production database."""
        self.print_step(1, "Backup Production Database")
        
        backup_file = self.backup_dir / f"backup_prod_{self.timestamp}.sql"
        
        if docker:
            print(f"Using Docker to backup database...")
            command = (
                f"docker exec fleet_postgres pg_dump "
                f"-U {self.settings.POSTGRES_USER} "
                f"{self.settings.POSTGRES_DB} > {backup_file}"
            )
        else:
            print(f"Backing up: {self.settings.DATABASE_URL}")
            command = (
                f"pg_dump -U {self.settings.POSTGRES_USER} "
                f"-h {self.settings.POSTGRES_HOST} "
                f"-p {self.settings.POSTGRES_PORT} "
                f"{self.settings.POSTGRES_DB} > {backup_file}"
            )
        
        self.run_command(command, f"Backup to {backup_file}")
        
        # Verify backup
        if backup_file.stat().st_size > 0:
            size_mb = backup_file.stat().st_size / (1024*1024)
            print(f"Backup size: {size_mb:.2f} MB")
            print(f"Backup location: {backup_file}")
            return str(backup_file)
        else:
            print(f"Backup file is empty!")
            sys.exit(1)
    
    def verify_connection(self):
        """Verify database connection."""
        self.print_step(2, "Verify Database Connection")
        
        try:
            from app.database.session import engine
            import sqlalchemy
            
            with engine.connect() as conn:
                result = conn.execute(sqlalchemy.text("SELECT version()"))
                version = result.fetchone()[0]
                print(f"Connected to database")
                print(f"PostgreSQL Version: {version[:50]}...")
            
            return True
        
        except Exception as e:
            print(f"Connection failed: {str(e)}")
            return False
    
    def check_migrations(self):
        """Check pending migrations."""
        self.print_step(3, "Check Pending Migrations")
        
        self.run_command(
            "python migrate.py history",
            "Show migration history",
            critical=False
        )
    
    def show_current_state(self):
        """Show current database state."""
        print(f"Current state:")
        self.run_command(
            "python migrate.py current",
            "Get current revision",
            critical=False
        )
    
    def deploy_migrations(self, docker=False):
        """Deploy migrations to production."""
        self.print_step(4, "Deploy Migrations")
        
        if docker:
            print(f"Deploying via Docker...")
            command = "docker exec -it service_manager python migrate.py upgrade head"
        else:
            command = "python migrate.py upgrade head"
        
        print(f"Upgrading to HEAD...")
        self.run_command(command, "Run migrations")
    
    def verify_deployment(self):
        """Verify migration deployment."""
        self.print_step(5, "Verify Deployment")
        
        print(f"Checking migration state...")
        self.run_command(
            "python migrate.py current",
            "Get current revision",
            critical=False
        )
        
        print(f"\nCounting database tables...")
        try:
            from app.database.session import engine
            import sqlalchemy
            
            inspector = sqlalchemy.inspect(engine)
            tables = inspector.get_table_names()
            
            print(f"Database has {len(tables)} tables")
            
            # Show critical tables
            critical_tables = ['tenants', 'drivers', 'bookings', 'vehicles']
            missing = [t for t in critical_tables if t not in tables]
            
            if missing:
                print(f"Warning: Missing tables: {missing}")
            else:
                print(f"All critical tables present")
            
            return True
        
        except Exception as e:
            print(f"Verification failed: {str(e)}")
            return False
    
    def rollback_migrations(self, steps=1):
        """Rollback migrations."""
        self.print_step(6, f"Rollback {steps} Migration(s)")
        
        for i in range(steps):
            print(f"Rolling back migration {i+1}/{steps}...")
            self.run_command(
                f"python migrate.py downgrade -1",
                f"Rollback step {i+1}",
                critical=False
            )
    
    def run_full_deployment(self, docker=False, skip_backup=False):
        """Run full deployment process."""
        self.print_header("PRODUCTION DEPLOYMENT")
        
        print(f"Database: {self.settings.DATABASE_URL}")
        print(f"Environment: {self.settings.ENV}")
        print(f"Timestamp: {self.timestamp}")
        print()
        
        # Confirm deployment
        if not skip_backup:
            response = input("WARNING: This will deploy to production. Continue? (yes/no): ").strip().lower()
            if response != "yes":
                print("Deployment cancelled")
                sys.exit(1)
        
        # Step 1: Backup
        if not skip_backup:
            backup_file = self.backup_database(docker=docker)
            print(f"Backup saved: {backup_file}\n")
        
        # Step 2: Verify connection
        if not self.verify_connection():
            sys.exit(1)
        
        # Step 3: Check migrations
        self.check_migrations()
        self.show_current_state()
        
        # Step 4: Deploy
        self.deploy_migrations(docker=docker)
        
        # Step 5: Verify
        if not self.verify_deployment():
            print("\nWarning: Verification issues detected")
        
        # Summary
        self.print_header("DEPLOYMENT COMPLETE")
        print("Migration deployment completed successfully!")
        print(f"Current revision: Check with: python migrate.py current")
        print(f"Rollback command: python migrate.py downgrade -1")
        print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Production deployment for database migrations"
    )
    
    parser.add_argument(
        "--docker",
        action="store_true",
        help="Use Docker containers for deployment"
    )
    
    parser.add_argument(
        "--env",
        help="Environment file to load (.env)"
    )
    
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Only backup database"
    )
    
    parser.add_argument(
        "--deploy",
        action="store_true",
        help="Run full deployment"
    )
    
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify current deployment state"
    )
    
    parser.add_argument(
        "--rollback",
        nargs="?",
        const=1,
        type=int,
        help="Rollback N migrations (default: 1)"
    )
    
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="Skip backup step (dangerous!)"
    )
    
    args = parser.parse_args()
    
    deployer = ProductionDeployer(env_file=args.env)
    
    if args.backup:
        deployer.backup_database(docker=args.docker)
    
    elif args.deploy:
        deployer.run_full_deployment(
            docker=args.docker,
            skip_backup=args.skip_backup
        )
    
    elif args.verify:
        deployer.verify_connection()
        deployer.show_current_state()
        deployer.verify_deployment()
    
    elif args.rollback is not None:
        deployer.rollback_migrations(steps=args.rollback)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
