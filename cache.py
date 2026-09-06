import os
import json
import hashlib
import time
import redis
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Initialize Redis client with graceful fallback
_redis_client = None

def _get_redis():
    """Lazy-initialize Redis connection. Returns None if Redis is unavailable."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        _redis_client = redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
            retry_on_timeout=True,
        )
        _redis_client.ping()
        print(f"[Redis] Connected successfully to {REDIS_URL.split('@')[-1] if '@' in REDIS_URL else 'localhost'}")
        return _redis_client
    except Exception as e:
        print(f"[Redis] Connection failed ({e}). App will run without cache (direct DB/API calls).")
        _redis_client = None
        return None


# ─── Core Cache Helpers ───────────────────────────────────────────────

def cache_get(key: str):
    """Get a cached JSON value by key. Returns None on miss or Redis error."""
    try:
        r = _get_redis()
        if r is None:
            return None
        raw = r.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        print(f"[Redis] GET error for '{key}': {e}")
        return None


def cache_set(key: str, data, ttl_seconds: int = 3600):
    """Set a JSON value in cache with TTL. Fails silently on Redis error."""
    try:
        r = _get_redis()
        if r is None:
            return
        r.setex(key, ttl_seconds, json.dumps(data, default=str))
    except Exception as e:
        print(f"[Redis] SET error for '{key}': {e}")


def cache_delete(key: str):
    """Delete a single cache key. Fails silently."""
    try:
        r = _get_redis()
        if r is None:
            return
        r.delete(key)
    except Exception as e:
        print(f"[Redis] DELETE error for '{key}': {e}")


def cache_delete_pattern(pattern: str):
    """Delete all keys matching a glob pattern (e.g. 'jobs:feed:*'). Fails silently."""
    try:
        r = _get_redis()
        if r is None:
            return
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor, match=pattern, count=100)
            if keys:
                r.delete(*keys)
            if cursor == 0:
                break
    except Exception as e:
        print(f"[Redis] DELETE_PATTERN error for '{pattern}': {e}")


# ─── Specialized Helpers ──────────────────────────────────────────────

def hash_text(text: str) -> str:
    """SHA-256 hash of text for use as cache key component."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def invalidate_user_cache(user_id: int):
    """Clear all cached data for a specific user (on resume upload, profile change, etc.)."""
    keys = [
        f"user:{user_id}:resume",
        f"user:{user_id}:ai_profile",
        f"user:{user_id}:resume_analysis",
        f"user:{user_id}:saved_jobs",
        f"user:{user_id}:profile",
    ]
    try:
        r = _get_redis()
        if r is None:
            return
        r.delete(*keys)
        print(f"[Redis] Invalidated all cache for user {user_id}")
    except Exception as e:
        print(f"[Redis] Error invalidating user {user_id} cache: {e}")


def invalidate_jobs_cache():
    """Clear all job-related caches (on scraper refresh)."""
    cache_delete("jobs:locations")
    cache_delete_pattern("jobs:feed:*")
    cache_delete_pattern("search:*")
    cache_delete_pattern("job:*")
    # Also clear all users' saved_jobs caches since saved_jobs references are deleted by scraper
    cache_delete_pattern("user:*:saved_jobs")
    print("[Redis] Invalidated all job caches (feed, locations, search, saved_jobs)")


# ─── Redis Rate Limiting (Sorted Sets) ───────────────────────────────

def rate_limit_check(key: str, max_requests: int, window_seconds: int = 60) -> bool:
    """
    Sliding window rate limiter using Redis Sorted Sets.
    Returns True if request is allowed, raises nothing.
    Returns False if rate limit exceeded.
    """
    try:
        r = _get_redis()
        if r is None:
            return True  # If Redis is down, allow (fallback to in-memory)

        now = time.time()
        window_start = now - window_seconds

        pipe = r.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)  # Remove expired entries
        pipe.zadd(key, {f"{now}": now})               # Add current request
        pipe.zcard(key)                                # Count requests in window
        pipe.expire(key, window_seconds + 10)          # Auto-cleanup TTL
        results = pipe.execute()

        current_count = results[2]
        if current_count > max_requests:
            # Remove the entry we just added since it's over limit
            r.zrem(key, f"{now}")
            return False
        return True
    except Exception as e:
        print(f"[Redis] Rate limit check error: {e}")
        return True  # Allow on Redis error


def token_bucket_consume(key: str, tokens: int, max_tokens: int, window_seconds: int = 3600):
    """
    Token rate limiter using Redis hash with sliding window.
    Returns (allowed: bool, remaining: int).
    """
    try:
        r = _get_redis()
        if r is None:
            return True, max_tokens  # If Redis is down, allow

        now = time.time()
        bucket_key = f"tokens:{key}"

        # Get current bucket state
        pipe = r.pipeline()
        pipe.hgetall(bucket_key)
        result = pipe.execute()
        bucket = result[0]

        window_start = now - window_seconds
        used = int(bucket.get("used", 0)) if bucket else 0
        last_reset = float(bucket.get("reset_at", 0)) if bucket else 0

        # Reset if window has passed
        if last_reset < window_start:
            used = 0

        if used + tokens > max_tokens:
            remaining = max(0, max_tokens - used)
            return False, remaining

        # Consume tokens
        pipe2 = r.pipeline()
        pipe2.hset(bucket_key, mapping={"used": used + tokens, "reset_at": str(now if last_reset < window_start else last_reset or now)})
        pipe2.expire(bucket_key, window_seconds + 60)
        pipe2.execute()

        remaining = max(0, max_tokens - (used + tokens))
        return True, remaining
    except Exception as e:
        print(f"[Redis] Token bucket error: {e}")
        return True, max_tokens


def token_bucket_remaining(key: str, max_tokens: int, window_seconds: int = 3600) -> int:
    """Get remaining tokens for a user without consuming any."""
    try:
        r = _get_redis()
        if r is None:
            return max_tokens

        now = time.time()
        bucket_key = f"tokens:{key}"
        bucket = r.hgetall(bucket_key)

        if not bucket:
            return max_tokens

        window_start = now - window_seconds
        last_reset = float(bucket.get("reset_at", 0))
        if last_reset < window_start:
            return max_tokens

        used = int(bucket.get("used", 0))
        return max(0, max_tokens - used)
    except Exception as e:
        print(f"[Redis] Token remaining check error: {e}")
        return max_tokens
