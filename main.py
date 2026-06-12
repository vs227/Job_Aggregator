from fastapi import FastAPI, Depends, HTTPException
from database import supabase
from auth import create_token, get_current_user, verify_password, hash_password
from models import RegisterUser, LoginUser, JobsInput, SavedJob, AlertPreference, SearchJob, SourceInput

app = FastAPI() 

@app.get("/")
def home():
    return{
        "message": "Welcome to the Job Aggregator service"
    }

@app.post("/register")
def register(user: RegisterUser):
    existing_user = (supabase.table("users").select("*").eq("email", user.email).execute())
    if existing_user.data:
        raise HTTPException(
            status_code=400,
            detail="Email already exists"
        )

    hashed = hash_password(user.password)
    new_user = (supabase.table("users").insert({
            "username": user.username,
            "email": user.email,
            "password_hash": hashed
        }).execute()
    )

    return {
        "message": "User registered successfully",
        "user": new_user.data[0]
    }

@app.post("/login")
def login(user: LoginUser):
    res = (supabase.table("users").select("*").eq("email", user.email).execute())

    if not res.data:
        raise HTTPException(
            status_code=401,
            detail="Invalid Email or Password"
        )
    db_user = res.data[0]

    if not verify_password(user.password, db_user["password_hash"]):
        raise HTTPException(
            status_code=401,
            detail="Invalid Email or Password"
        )

    token = create_token({"user_id": db_user["id"], "email": db_user["email"]})

    return {
        "message": "Login successful",
        "access_token": token,
        "token_type": "bearer"
    }