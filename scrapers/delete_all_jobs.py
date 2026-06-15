import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from database import supabase

def main():
    confirm = input("Are you sure you want to delete ALL jobs? (yes/no): ")
    if confirm.lower() == "yes":
        try:
            supabase.table("jobs").delete().neq("id", 0).execute()
            print("All jobs deleted!")
        except Exception as e:
            print(f"Error deleting jobs: {e}")
    else:
        print("Deletion canceled.")

if __name__ == "__main__":
    main()
