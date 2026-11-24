"""
HireNexa Built-in Technical & Career Intelligence Engine
Provides authoritative, production-grade technical explanations, interview questions,
architectural designs, and career guidance directly within HireNexa without external redirects.
"""

import re
from typing import Optional


class TechnicalKnowledgeEngine:
    """
    Comprehensive offline knowledge engine providing deep explanations,
    syntax-highlighted code blocks, and vetted interview question banks.
    """

    @classmethod
    def get_technical_response(cls, user_message: str, mode: str = "GENERAL", language: str = "en") -> Optional[str]:
        """
        Analyzes the user's inquiry. If it matches a technical concept, coding topic,
        or interview question request, returns a thorough, beautifully formatted response.
        """
        msg = user_message.lower().strip()

        # 1. PYTHON DECORATORS
        if "decorator" in msg and "python" in msg or msg in ["explain python decorators", "explain decorator", "what is a decorator in python", "python decorators"]:
            return cls._explain_python_decorators()

        # 2. 20 DJANGO INTERVIEW QUESTIONS
        if ("django" in msg and "interview" in msg) or "20 django interview questions" in msg or "django interview question" in msg:
            return cls._django_interview_questions()

        # 3. 20 PYTHON INTERVIEW QUESTIONS
        if ("python" in msg and "interview" in msg) or "20 python interview questions" in msg or "python interview question" in msg:
            return cls._python_interview_questions()

        # 4. PYTHON GENERATORS & YIELD
        if "generator" in msg or "yield" in msg and "python" in msg:
            return cls._explain_python_generators()

        # 5. DJANGO ORM: SELECT_RELATED VS PREFETCH_RELATED
        if "select_related" in msg or "prefetch_related" in msg or ("django orm" in msg and "optimize" in msg):
            return cls._explain_django_orm_optimization()

        # 6. DJANGO ARCHITECTURE & MTV PATTERN
        if "django" in msg and ("mtv" in msg or "mvc" in msg or "architecture" in msg or "how django works" in msg):
            return cls._explain_django_architecture()

        # 7. REACT HOOKS & USEEFFECT LIFECYCLE
        if "react" in msg and ("hook" in msg or "useeffect" in msg or "lifecycle" in msg or "virtual dom" in msg or "reconciliation" in msg):
            return cls._explain_react_architecture()

        # 8. BINARY SEARCH IMPLEMENTATION
        if "binary search" in msg:
            return cls._explain_binary_search()

        # 9. ASYNC / AWAIT & CONCURRENCY
        if "async" in msg and ("await" in msg or "event loop" in msg or "concurrency" in msg or "coroutine" in msg):
            return cls._explain_async_await()

        # 10. SQL INDEXING & QUERY OPTIMIZATION
        if ("sql" in msg or "database" in msg) and ("index" in msg or "query optimization" in msg or "explain analyze" in msg or "acid" in msg):
            return cls._explain_sql_optimization()

        # 11. REST API DESIGN & HTTP STATUS CODES
        if "rest" in msg and ("api" in msg or "endpoint" in msg or "status code" in msg or "idempotent" in msg):
            return cls._explain_rest_api_design()

        # 12. DOCKER & CONTAINERIZATION
        if "docker" in msg and ("container" in msg or "dockerfile" in msg or "compose" in msg):
            return cls._explain_docker()

        # 13. GIT & VERSION CONTROL
        if "git" in msg and ("rebase" in msg or "merge" in msg or "cherry-pick" in msg or "workflow" in msg):
            return cls._explain_git_workflows()

        # 14. RESUME OPTIMIZATION & ATS SCORING
        if "resume" in msg and ("ats" in msg or "improve" in msg or "tips" in msg or "checklist" in msg or "format" in msg):
            return cls._explain_resume_optimization()

        # 15. CODING MODE GENERIC TECHNICAL FRAMEWORK
        if mode == "CODING" and any(k in msg for k in ["code", "function", "class", "algorithm", "debug", "error", "script", "syntax"]):
            return cls._generic_coding_framework(user_message)

        return None

    # ==========================================================================
    # DETAILED TOPIC GENERATORS
    # ==========================================================================

    @classmethod
    def _explain_python_decorators(cls) -> str:
        return """### 🐍 In-Depth Guide: Python Decorators

In Python, a **decorator** is a design pattern that allows you to dynamically extend or modify the behavior of a function or method **without permanently altering its source code**.

At their core, decorators are **higher-order functions**—functions that accept another function as an argument, define an inner wrapper function that adds functionality, and return that wrapper.

---

### 1. Conceptual Foundation: Functions as First-Class Citizens

In Python, functions are first-class objects:
1. They can be assigned to variables.
2. They can be passed as arguments to other functions.
3. They can be returned from other functions.
4. They can be defined inside other functions (**closures**).

```python
def greet(name):
    return f"Hello, {name}!"

# Functions can be referenced and passed
say_hello = greet
print(say_hello("Alex"))  # "Hello, Alex!"
```

---

### 2. Anatomy of a Decorator

The `@decorator_name` syntax is simply **syntactic sugar** for:
`target_function = decorator_name(target_function)`

```python
import functools
import time

def execution_logger(func):
    \"\"\"
    A decorator that logs function execution time and arguments.
    @functools.wraps preserves the original function's name and docstring.
    \"\"\"
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        print(f"⚡ [START] Executing '{func.__name__}' with args={args}, kwargs={kwargs}")
        
        # Call the original wrapped function
        result = func(*args, **kwargs)
        
        elapsed = (time.perf_counter() - start_time) * 1000
        print(f"✓ [FINISH] '{func.__name__}' completed in {elapsed:.3f} ms. Result: {result}")
        return result
    
    return wrapper

# Using the decorator with '@' syntax
@execution_logger
def calculate_factorial(n: int) -> int:
    \"\"\"Calculates factorial recursively.\"\"\"
    if n <= 1:
        return 1
    total = 1
    for i in range(2, n + 1):
        total *= i
    return total

# Execution
res = calculate_factorial(5)
# Output:
# ⚡ [START] Executing 'calculate_factorial' with args=(5,), kwargs={}
# ✓ [FINISH] 'calculate_factorial' completed in 0.008 ms. Result: 120
```

---

### 3. Production Use Cases in Enterprise Development

#### A. Role-Based Access Control (RBAC) in Web Frameworks (e.g. Django/FastAPI)

```python
import functools
from django.core.exceptions import PermissionDenied

def require_role(allowed_roles: list[str]):
    \"\"\"
    Parameterized decorator: Checks if authenticated user has one of the required roles.
    \"\"\"
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                raise PermissionDenied("Authentication required.")
            
            if request.user.role not in allowed_roles:
                raise PermissionDenied(f"Access restricted to roles: {', '.join(allowed_roles)}")
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

# Usage on view endpoints:
# @require_role(["RECRUITER", "COMPANY_ADMIN", "OWNER"])
# def publish_vacancy(request): ...
```

#### B. In-Memory Memoization & Caching

```python
import functools

def memoize(func):
    \"\"\"Caches results of pure functions based on arguments.\"\"\"
    cache = {}
    @functools.wraps(func)
    def wrapper(*args):
        if args in cache:
            return cache[args]
        result = func(*args)
        cache[args] = result
        return result
    wrapper.cache = cache
    return wrapper

@memoize
def fibonacci(n: int) -> int:
    if n < 2:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

print(fibonacci(35))  # Instantaneous due to O(n) cache lookup instead of O(2^n)
```

---

### 4. Key Rules & Best Practices

1. **Always use `@functools.wraps(func)`**: Without it, the decorated function loses its `__name__`, `__doc__`, and parameter signature, breaking documentation generators and debugging tools.
2. **Accept `*args, **kwargs`** in the inner wrapper to ensure your decorator works with functions having any number of positional or keyword arguments.
3. **Always return the wrapper's return value**: Ensure the wrapper captures and returns `result = func(*args, **kwargs)` so the calling code receives the expected output.
4. **Clean Parameterization**: If your decorator needs its own arguments (e.g. `@retry(max_attempts=3)`), wrap it in an additional outer function that returns the decorator.

---

### Next Steps to Explore:
- Would you like to see how to implement **Class Decorators** with `__call__`?
- Should we examine **Async Decorators** for `async def` coroutines in Python?
"""

    @classmethod
    def _django_interview_questions(cls) -> str:
        return """### 🎯 20 Enterprise Django Interview Questions & In-Depth Technical Answers

Here is a curated, production-vetted question bank covering the Django web framework, ORM optimization, architecture, security, and scalability.

---

#### 1. What is the difference between Django's MTV and traditional MVC architecture?
- **MVC**: Model (Data/Business Logic), View (User Interface rendering), Controller (Request Router & Business Glue).
- **MTV**: 
  - **Model**: Data access layer handled by Django ORM.
  - **Template**: Presentation layer rendering HTML/UI (equivalent to MVC View).
  - **View**: Request-handling controller logic (equivalent to MVC Controller). The Django framework itself acts as the overall Controller routing requests through `urls.py`.

---

#### 2. Explain the difference between `select_related()` and `prefetch_related()`.
- **`select_related`**:
  - Works on single-valued relationships: **ForeignKey** and **OneToOneField**.
  - Performs a single SQL query using an **`INNER JOIN`** or **`LEFT OUTER JOIN`**.
  - Loads related objects into memory immediately.
- **`prefetch_related`**:
  - Works on multi-valued relationships: **ManyToManyField** and reverse **ForeignKey**.
  - Executes **two or more separate SQL queries** and performs the lookup/joining in Python memory using `IN (...)`.
  - Avoids the dreaded **N+1 query problem**.

```python
# select_related (1 SQL Query with JOIN):
jobs = Job.objects.select_related('organization').all()

# prefetch_related (2 SQL Queries):
jobs = Job.objects.prefetch_related('requirements').all()
```

---

#### 3. What is the N+1 queries problem and how do you diagnose and eliminate it in Django?
- **Problem**: When iterating over $N$ parent objects and accessing a related foreign key attribute inside a loop, Django executes 1 query to fetch the parent list, plus $N$ additional queries (one per item).
- **Diagnosis**: Use `django-debug-toolbar`, `django.db.connection.queries`, or database query logging.
- **Solution**: Apply `.select_related()` for `1:1` or `FK` relationships, and `.prefetch_related()` for `M:M` or reverse `FK` relationships.

---

#### 4. What are Django `Q` objects and when should you use them?
`Q` objects encapsulate SQL query conditions that can be combined using logical operators (`&` AND, `|` OR, `~` NOT). They are necessary for executing complex SQL `WHERE` clauses with `OR` conditions.

```python
from django.db.models import Q

# Find active jobs that either have "Python" in the title OR "Remote" workplace type
openings = Job.objects.filter(
    Q(title__icontains="Python") | Q(workplace_type="REMOTE"),
    is_active=True
)
```

---

#### 5. What are Django `F` expressions and why are they important for concurrency?
`F()` represents the value of a model field directly in the database, allowing operations to happen on the database server without pulling values into Python memory.
- **Benefits**:
  1. Prevents **race conditions**: Multiple threads incrementing a count won't overwrite each other.
  2. Performance: Avoids loading large columns into Python memory just to increment them.

```python
from django.db.models import F

# Atomic increment directly on PostgreSQL/SQLite
Job.objects.filter(id=42).update(views_count=F('views_count') + 1)
```

---

#### 6. What is the role of Django Middleware and what is its execution order?
Middleware is a lightweight plugin system that intercepts globally every incoming HTTP request and outgoing HTTP response.
- **Execution Order**:
  - **Request Phase**: Executed top-to-bottom as listed in `settings.MIDDLEWARE`.
  - **Response Phase**: Executed bottom-to-top in reverse order.
- Typical duties: Session handling (`SessionMiddleware`), Authentication (`AuthenticationMiddleware`), CSRF verification (`CsrfViewMiddleware`), Security headers (`SecurityMiddleware`), and Rate Limiting.

---

#### 7. How does Django's CSRF protection mechanism work?
1. Django issues a cryptographically secure random token stored in a cookie (`csrftoken`).
2. For state-mutating requests (`POST`, `PUT`, `DELETE`, `PATCH`), the client must supply the matching token via a hidden form input (`{% csrf_token %}`) or an HTTP header (`X-CSRFToken`).
3. Django's `CsrfViewMiddleware` verifies that the cookie token and the submitted token match using masked comparisons. If mismatched or absent, HTTP 403 Forbidden is returned.

---

#### 8. How does `transaction.atomic()` work and when should you use it?
`transaction.atomic()` creates a database transaction block (or savepoint in nested blocks). If an exception is raised within the block, all database mutations inside it are rolled back; if the block exits successfully, they are committed.

```python
from django.db import transaction

with transaction.atomic():
    application = Application.objects.create(candidate=user, job=job)
    job.headcount_filled += 1
    job.save()
    Notification.objects.create(user=job.recruiter, message="New applicant.")
```

---

#### 9. What is the difference between `aggregate()` and `annotate()` in Django ORM?
- **`aggregate()`**: Computes a summary value across the **entire QuerySet** and returns a Python dictionary (e.g. `Avg('salary')`, `Count('id')`).
- **`annotate()`**: Adds a per-row calculated column to **each individual object** in the QuerySet, equivalent to SQL `GROUP BY`.

```python
from django.db.models import Count, Avg

# aggregate -> Single summary dict: {'avg_salary': 850000.0}
stats = Job.objects.aggregate(avg_salary=Avg('salary_max'))

# annotate -> QuerySet where each Company has an 'open_jobs' attribute
companies = Organization.objects.annotate(open_jobs=Count('jobs'))
```

---

#### 10. Why should you customize the `User` model at the start of a Django project?
Django's default `auth.User` uses `username` and lacks custom fields like roles, phone numbers, or multi-tenant organizations. Changing the user model mid-project requires complex database migrations. Using `AbstractUser` or `AbstractBaseUser` from day one allows adding custom RBAC enums (`Role.RECRUITER`, `Role.CANDIDATE`), email authentication, and multi-factor flags cleanly.

---

#### 11. What is the difference between Django Signals and Model Methods?
- **Model Methods (`save()`, `clean()`)**: Best for logic tightly coupled to the model instance itself (validating fields, updating timestamps).
- **Signals (`post_save`, `pre_delete`)**: Best for decoupled side effects where other apps need to listen to model events without circular imports (e.g. sending an audit log, clearing cache, dispatching an email notification).

---

#### 12. How do you implement database indexing in Django models?
Use `indexes` inside the model's `Meta` class:

```python
class Job(models.Model):
    title = models.CharField(max_length=200)
    location = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=['is_active', 'title']),
            models.Index(fields=['location']),
        ]
```

---

#### 13. What is the difference between `null=True` and `blank=True`?
- **`null=True`**: Database-level constraint. Sets the column to allow `NULL` values in PostgreSQL/MySQL/SQLite.
- **`blank=True`**: Validation-level constraint. Controls whether the field is required in Django forms and the admin interface.
- *Best practice for string fields (`CharField`, `TextField`)*: Avoid `null=True` to prevent having two representations for empty data (`NULL` and `""`). Use `blank=True` with `default=""`.

---

#### 14. What are Django REST Framework Serializers and how do they differ from ModelSerializers?
- **`Serializer`**: General serializer that defines explicit fields and explicit `create()` and `update()` logic.
- **`ModelSerializer`**: Shortcut that automatically maps fields from a Django ORM model, automatically configures field validators, and provides default `create()` and `update()` implementations.

---

#### 15. How do you handle file uploads securely in Django?
1. Validate file extension and MIME type via magic bytes inspection (not just file name).
2. Enforce file size limits (e.g. 5MB) before processing.
3. Generate sanitized, randomized, or hashed file names (`uuid.uuid4()`) to prevent directory traversal (`../../`).
4. Store files in private storage (e.g. Supabase Storage / AWS S3) rather than public web roots, and serve via temporary signed URLs.

---

#### 16. What is the difference between `defer()` and `only()`?
- **`only('col1', 'col2')`**: Instructs the ORM to load **only** the specified fields in the initial SQL `SELECT`. Other fields are deferred and lazily loaded on demand.
- **`defer('col3')`**: Instructs the ORM to load all fields **except** the specified heavy columns (e.g. large `TextField` or JSON).

---

#### 17. How do you manage database migrations safely in production without downtime?
1. Follow **Expand and Contract**: Never delete or rename a column in the same release.
2. In step 1, add the new nullable column and update application code to write to both.
3. In step 2, backfill existing rows.
4. In step 3, update application code to read from the new column.
5. In step 4, remove the old column.
6. Always back up the database before running migrations (`python manage.py migrate`).

---

#### 18. What is the difference between WSGI and ASGI in Django?
- **WSGI (Web Server Gateway Interface)**: Synchronous, blocking request-response standard (e.g. Gunicorn, uWSGI).
- **ASGI (Asynchronous Server Gateway Interface)**: Asynchronous standard supporting WebSockets, long polling, Server-Sent Events (SSE), and async request handling (e.g. Uvicorn, Daphne).

---

#### 19. How do you implement caching in Django?
Django supports multiple cache backends (Redis, Memcached, Database, Local Memory).
- **Per-site caching**: Via `UpdateCacheMiddleware` and `FetchFromCacheMiddleware`.
- **Per-view caching**: Via `@cache_page(60 * 15)`.
- **Low-level cache API**: `from django.core.cache import cache; cache.get(key); cache.set(key, val, timeout=300)`.

---

#### 20. What critical security headers should be configured for production Django?
```python
# settings.py
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
```

---

### Recommended Next Steps:
- Would you like to practice mock technical interviews on any of these specific Django topics?
- We can explore **Django REST Framework Serializer performance**, **Celery background tasks**, or **Dockerizing Django with PostgreSQL**!
"""

    @classmethod
    def _python_interview_questions(cls) -> str:
        return r"""### 🐍 20 Senior Python Interview Questions & Detailed Technical Answers

A comprehensive technical preparation guide covering Python internals, memory model, concurrency, data structures, and advanced language idioms.

---

#### 1. What is the Global Interpreter Lock (GIL) and how does it affect multi-threaded Python programs?
The **GIL** is a mutex (mutual exclusion lock) used by CPython to ensure that only one native thread executes Python bytecode at any given moment.
- **Why it exists**: CPython's memory management is not thread-safe; the GIL protects reference counts and internal memory structures from race conditions.
- **Impact**: CPU-bound multi-threaded code in Python will not run in parallel across multiple CPU cores.
- **Solutions**:
  1. For **CPU-bound tasks**: Use `multiprocessing` or `concurrent.futures.ProcessPoolExecutor` to spawn separate processes with independent memory spaces and GILs.
  2. For **I/O-bound tasks**: Use `threading` or `asyncio` because Python releases the GIL during network/disk I/O and sleep operations.
  3. C extensions (NumPy, Cython) can explicitly release the GIL during heavy numeric computations.

---

#### 2. How does Python's memory management and garbage collection work?
Python uses a dual-mechanism memory architecture:
1. **Reference Counting (Primary)**: Every Python object has an internal `ob_refcnt`. When a reference is created, it increments; when deleted or goes out of scope, it decrements. When it hits zero, memory is deallocated immediately.
2. **Generational Cyclic Garbage Collector (Secondary)**: Reference counting alone cannot handle **circular references** (e.g., `A.b = B; B.a = A`). Python's `gc` module periodically scans objects divided into three generations (`Gen 0`, `Gen 1`, `Gen 2`), detecting cycles of unreachable objects and freeing them.

---

#### 3. What is the difference between `deepcopy` and `shallow copy`?
- **Shallow Copy (`copy.copy()` or `list.copy()`)**: Creates a new outer compound object, but inserts references to the original nested objects. Modifying a nested mutable object in the copy affects the original.
- **Deep Copy (`copy.deepcopy()`)**: Recursively copies both the outer object and all nested objects, creating completely independent duplicate structures in memory.

---

#### 4. What are Generators, how does `yield` work, and what are their memory benefits?
A generator is a function containing one or more `yield` statements that returns an **iterator object**.
- When called, execution pauses at `yield`, yielding the value and saving the entire function frame/state on the stack.
- On the next `next()` call, execution resumes immediately after the `yield`.
- **Memory benefit**: Lazily computes items on demand ($O(1)$ memory) rather than creating a massive list in RAM ($O(N)$ memory).

```python
# 1 Million numbers takes negligible memory with a generator:
def number_stream(n):
    for i in range(n):
        yield i
```

---

#### 5. What are `*args` and `**kwargs` and how does parameter unpacking work?
- `*args`: Collects extra positional arguments into a **tuple**.
- `**kwargs`: Collects extra keyword arguments into a **dictionary**.
- In call sites, `*` unpacks an iterable into positional parameters, and `**` unpacks a dictionary into keyword arguments.

---

#### 6. What is the difference between mutable and immutable types in Python?
- **Mutable**: Values can be changed in place without changing memory address (`id()`). Examples: `list`, `dict`, `set`, custom classes.
- **Immutable**: Cannot be modified after creation; any modification produces a brand-new object. Examples: `int`, `float`, `str`, `tuple`, `frozenset`, `bytes`.
- **Implication**: Only immutable objects can be used as dictionary keys and set elements because their hash value must remain constant.

---

#### 7. How do Context Managers and the `with` statement work under the hood?
Context managers implement the Context Management Protocol consisting of two methods:
1. `__enter__()`: Sets up resources and optionally returns an object assigned via `as`.
2. `__exit__(exc_type, exc_val, exc_tb)`: Tears down resources, runs cleanup, and handles any exceptions raised within the block.

```python
class ManagedResource:
    def __enter__(self):
        print("Acquiring lock / connection...")
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        print("Releasing lock / closing connection...")
        return False  # Propagate exceptions if any
```

---

#### 8. What is the difference between `is` and `==`?
- `==`: Checks for **equality of values** (calls `__eq__()`).
- `is`: Checks for **identity in memory** (compares `id(a) == id(b)`).

```python
a = [1, 2, 3]
b = [1, 2, 3]
print(a == b)  # True (equal content)
print(a is b)  # False (different heap locations)
```

---

#### 9. What are Python Dunder (Magic) Methods and how do they enable operator overloading?
Dunder ("double underscore") methods are reserved hooks that CPython invokes for special syntax:
- `__init__`: Constructor initializer.
- `__str__` / `__repr__`: String representations.
- `__len__`: Invoked by `len(obj)`.
- `__getitem__`: Invoked by `obj[key]`.
- `__add__`: Invoked by `+` operator.

---

#### 10. Explain the Method Resolution Order (MRO) and C3 Linearization.
When resolving attribute or method lookups in multiple inheritance hierarchies, Python uses the **C3 Linearization Algorithm** to guarantee:
1. Children precede their parents.
2. The order of parent classes in the class definition is preserved.
3. Every class is evaluated once without ambiguity.
Inspect with `ClassName.mro()` or `ClassName.__mro__`.

---

#### 11. What are Metaclasses and what is their practical purpose?
A metaclass is the "class of a class"—classes are instances of metaclasses. The default metaclass is `type`.
- Custom metaclasses override `__new__` or `__init__` to inspect, alter, or validate class creation at module load time.
- Used heavily in ORMs (like Django ORM) to convert class attributes into database table columns.

---

#### 12. What is the difference between `@staticmethod` and `@classmethod`?
- **`@classmethod`**: Receives the class itself as the first parameter (`cls`). Can modify class state and acts as an alternative constructor factory.
- **`@staticmethod`**: Receives neither `self` nor `cls`. Behaves like a plain function scoped inside the class namespace for logical grouping.

---

#### 13. What is monkey patching and why is it considered an anti-pattern in production?
Monkey patching is the runtime modification of a class or module's attributes/methods dynamically. While useful in unit test mocking, doing it in production creates unpredictable side effects, breaks static analysis, and makes debugging difficult.

---

#### 14. What are `__slots__` and why are they used?
By default, Python stores an object's instance attributes in a dynamic `__dict__`, which incurs memory overhead. Defining `__slots__ = ('name', 'age')` reserves space for a fixed set of attributes, drastically reducing memory usage when creating millions of small instances and accelerating attribute access.

---

#### 15. How does `asyncio` achieve cooperative multitasking?
`asyncio` runs a single-threaded **event loop**. When an asynchronous task encounters an `await` on an I/O operation (socket, timer), it yields control back to the event loop. The loop switches to other ready tasks while waiting for the I/O to complete.

---

#### 16. What is the difference between `list.sort()` and `sorted()`?
- `list.sort()`: In-place sort modifying the original list; returns `None`. Time complexity: $O(N \log N)$ (Timsort).
- `sorted(iterable)`: Returns a new sorted list leaving the original iterable unmodified. Works on any iterable (strings, tuples, dicts).

---

#### 17. How do lambda functions differ from regular functions?
Lambda functions are anonymous, inline functions restricted to a single expression whose evaluated value is automatically returned. They cannot contain statements (`return`, `raise`, `try/except`) or type annotations.

---

#### 18. What is the difference between `itertools` and built-in list processing?
`itertools` provides memory-efficient, fast C-implemented iterators for combinatorial, infinite, and grouping logic (`chain`, `cycle`, `combinations`, `groupby`), computing values lazily on the fly.

---

#### 19. What are Type Hints and the `typing` module in modern Python?
Introduced in PEP 484 (Python 3.5+), type hints (`def process(name: str, count: int) -> bool:`) provide static type documentation for IDE autocompletion, type checkers (mypy, pyright), and runtime validation libraries (Pydantic). They do not enforce types at CPython runtime.

---

#### 20. How do you profile and optimize Python performance?
1. **Measurement**: Profile before optimizing using `cProfile`, `timeit`, and `memory_profiler`.
2. **Algorithmic efficiency**: Replace $O(N^2)$ loops with $O(N \log N)$ or $O(N)$ hash lookups (`set` / `dict`).
3. **Built-ins**: Use C-optimized built-ins (`map`, `filter`, list comprehensions, `collections.deque`).
4. **Vectorization**: Offload heavy math to NumPy.
5. **JIT / Compilation**: Use PyPy or Cython/Numba when CPU performance is critical.
"""

    @classmethod
    def _explain_python_generators(cls) -> str:
        return """### ⚡ Python Generators & the `yield` Keyword: Memory & Performance

A **generator** is a special type of iterator function that produces a sequence of values lazily on demand using the `yield` statement rather than calculating everything upfront and storing it in memory.

---

### 1. The Problem with Eager Evaluation (Lists)

When generating a large dataset with a standard list, all elements must fit simultaneously into RAM:

```python
import sys

# Creating a list of 10 million integers in memory:
huge_list = [i for i in range(10_000_000)]
print(f"List Memory: {sys.getsizeof(huge_list) / (1024 * 1024):.2f} MB")
# Output: ~80 MB of RAM consumed immediately!
```

---

### 2. The Generator Solution ($O(1)$ Space Complexity)

```python
import sys

def number_generator(n):
    for i in range(n):
        yield i

gen = number_generator(10_000_000)
print(f"Generator Memory: {sys.getsizeof(gen)} Bytes")
# Output: ~200 Bytes regardless of whether n is 10 or 10 Billion!
```

---

### 3. Real-World Enterprise Example: Streaming Log File Analysis

```python
def stream_large_log_file(file_path):
    \"\"\"Reads a multi-gigabyte server access log file line by line.\"\"\"
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            if "ERROR" in line or "CRITICAL" in line:
                yield line.strip()

# Pipeline processing without crashing memory
for error_log in stream_large_log_file("/var/log/nginx/access.log"):
    # Process each log entry one by one
    print(f"Incident Alert: {error_log}")
```

---

### 4. Generator Expressions & `yield from`

```python
# Generator Expression (parentheses instead of brackets)
squares_gen = (x**2 for x in range(1_000_000))

# 'yield from' delegates generation to a sub-generator
def chained_streams(*iterables):
    for it in iterables:
        yield from it
```
"""

    @classmethod
    def _explain_django_orm_optimization(cls) -> str:
        return """### 🚀 Django ORM Optimization: `select_related` vs `prefetch_related`

The #1 performance bottleneck in Django applications is the **N+1 Database Query problem**. Mastering `select_related` and `prefetch_related` is essential for production scalability.

---

### 1. `select_related` (Single Query JOIN)
- **Use for**: `ForeignKey` and `OneToOneField` (single related object).
- **Mechanism**: Generates an SQL `INNER JOIN` or `LEFT OUTER JOIN`.

```python
# ❌ BAD: 1 query for all jobs + 100 queries for company names (101 queries!)
jobs = Job.objects.filter(is_active=True)[:100]
for j in jobs:
    print(j.organization.name)

# ✅ OPTIMIZED: Exactly 1 SQL Query with INNER JOIN
jobs = Job.objects.filter(is_active=True).select_related('organization')[:100]
for j in jobs:
    print(j.organization.name)
```

---

### 2. `prefetch_related` (Multi-Query In-Memory Joining)
- **Use for**: `ManyToManyField` and reverse `ForeignKey` (multiple related objects).
- **Mechanism**: Executes 2 separate SQL queries and joins records in Python memory.

```python
# ✅ OPTIMIZED: 2 Queries Total (1 for jobs, 1 for all requirements in IN (...))
jobs = Job.objects.filter(is_active=True).prefetch_related('requirements')
for j in jobs:
    for req in j.requirements.all():
        print(req.skill_name)
```

---

### 3. Cheat Sheet for High-Performance Queries

| Tool | Purpose | Example |
| :--- | :--- | :--- |
| `select_related()` | Single-valued JOIN (`FK`, `1:1`) | `Job.objects.select_related('organization')` |
| `prefetch_related()` | Multi-valued lookup (`M:M`, reverse `FK`) | `User.objects.prefetch_related('applications')` |
| `only()` | Load only specific columns | `Job.objects.only('id', 'title', 'salary')` |
| `defer()` | Avoid loading huge columns | `CandidateProfile.objects.defer('raw_resume_text')` |
| `bulk_create()` | Insert 1,000 rows in 1 query | `Question.objects.bulk_create(questions_list)` |
| `bulk_update()` | Update specified fields in 1 query | `Job.objects.bulk_update(jobs, ['status'])` |
"""

    @classmethod
    def _explain_django_architecture(cls) -> str:
        return """### 🏛️ Django Architecture & Request-Response Lifecycle

Django follows the **Model-Template-View (MTV)** pattern, wrapped in WSGI/ASGI middleware and a URL routing dispatcher.

---

### The Complete Request-Response Lifecycle:

```text
HTTP Request
     │
     ▼
[WSGI / ASGI Gateway] (Gunicorn, Uvicorn)
     │
     ▼
[Security & Global Middleware (Request Phase)]
     ├── SecurityMiddleware
     ├── SessionMiddleware
     ├── CommonMiddleware
     ├── CsrfViewMiddleware
     └── AuthenticationMiddleware
     │
     ▼
[URL Dispatcher (urls.py)] -> Matches route and extracts parameters
     │
     ▼
[View Layer (views.py)]
     ├── Calls Django ORM (models.py) <-> Database (PostgreSQL / SQLite)
     ├── Executes Business Logic, Services, AI Matchers
     └── Renders Template (templates/*.html) OR returns JSON (DRF)
     │
     ▼
[Middleware (Response Phase)] -> Headers attached, cookies serialized
     │
     ▼
HTTP Response (HTML / JSON) -> Browser / Mobile Client
```
"""

    @classmethod
    def _explain_react_architecture(cls) -> str:
        return """### ⚛️ Modern React Architecture: Hooks, Virtual DOM & Lifecycle

React is a declarative, component-based library for building user interfaces.

---

### 1. React Hooks Essentials

#### `useEffect`: Managing Side Effects
```javascript
import React, { useState, useEffect } from 'react';

function JobSearchLive() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Debounce API calls by 300ms
    const timer = setTimeout(async () => {
      if (!query.trim()) return;
      setLoading(true);
      try {
        const res = await fetch(`/api/v1/jobs/?q=${encodeURIComponent(query)}`);
        const data = await res.json();
        setResults(data.results || []);
      } catch (err) {
        console.error("Search failed:", err);
      } finally {
        setLoading(false);
      }
    }, 300);

    // Cleanup function runs before next effect execution or unmount
    return () => clearTimeout(timer);
  }, [query]); // Dependency array: only re-run when query changes
```

---

### 2. The Virtual DOM & Reconciliation (React Fiber)
1. When state changes (`setState`), React re-renders the component to produce a new **Virtual DOM tree** in JavaScript memory.
2. The **Diffing Algorithm (Heuristic O(n))** compares the new Virtual DOM with the previous snapshot:
   - Elements of different types produce completely new subtrees.
   - Child lists use `key` attributes to identify which items were moved, added, or removed.
3. Only the minimal necessary mutations are committed to the actual browser DOM in the **Commit Phase**.
"""

    @classmethod
    def _explain_binary_search(cls) -> str:
        return r"""### 🔍 Binary Search Algorithm: Implementation & Analysis

Binary Search finds the position of a target value within a **sorted array** in logarithmic time: $O(\log N)$.

---

### 1. Iterative Implementation in Python

```python
def binary_search(arr: list[int], target: int) -> int:
    \"\"\"
    Searches for target in sorted array 'arr'.
    Returns index if found, or -1 if not present.
    Time Complexity: O(log n)
    Space Complexity: O(1)
    \"\"\"
    left = 0
    right = len(arr) - 1

    while left <= right:
        # Prevents integer overflow in languages like C++/Java:
        mid = left + (right - left) // 2

        if arr[mid] == target:
            return mid  # Target found
        elif arr[mid] < target:
            left = mid + 1  # Search right half
        else:
            right = mid - 1  # Search left half

    return -1  # Target not found

# Example execution:
numbers = [2, 5, 8, 12, 16, 23, 38, 56, 72, 91]
idx = binary_search(numbers, 23)
print(f"Target 23 found at index: {idx}")  # Output: 5
```

---

### 2. Complexity Analysis:
- **Best Case**: $O(1)$ (Target is at the exact midpoint).
- **Average & Worst Case**: $O(\log_2 N)$ (Search space halved each step).
- **Space Complexity**: $O(1)$ for iterative, $O(\log N)$ for recursive call stack.
"""

    @classmethod
    def _explain_async_await(cls) -> str:
        return """### ⚡ Async/Await and Event-Driven Concurrency

`async` and `await` allow writing concurrent, non-blocking code using a readable sequential syntax.

---

### Python `asyncio` Example: Parallel API Fetching

```python
import asyncio
import httpx

async def fetch_organization_data(org_id: int):
    async with httpx.AsyncClient() as client:
        print(f"Requesting Org {org_id}...")
        resp = await client.get(f"https://api.hirenexa.com/v1/orgs/{org_id}/")
        return resp.json()

async def main():
    # Execute 3 network requests concurrently in the event loop:
    results = await asyncio.gather(
        fetch_organization_data(101),
        fetch_organization_data(102),
        fetch_organization_data(103),
    )
    print("All org records retrieved:", len(results))

# Run the event loop
asyncio.run(main())
```
"""

    @classmethod
    def _explain_sql_optimization(cls) -> str:
        return r"""### 🗄️ Database Query Optimization & Indexing Strategies

High-scale database performance in PostgreSQL and relational systems relies on intelligent schema indexing and query planning.

---

### 1. B-Tree Indexes vs Sequential Scans
- Without an index, the database performs a **Full Table Scan (Seq Scan)**: $O(N)$ row evaluations.
- With a **B-Tree Index**, lookups take $O(\log N)$ tree traversals.

```sql
-- Creating composite index for high-cardinality search:
CREATE INDEX idx_jobs_active_created ON recruitment_job (is_active, created_at DESC);
```

---

### 2. Using `EXPLAIN ANALYZE` in PostgreSQL
Always inspect the query execution plan before optimizing:
```sql
EXPLAIN ANALYZE
SELECT id, title, location 
FROM recruitment_job 
WHERE is_active = TRUE AND location = 'Bhubaneswar';
```
Look for:
- `Seq Scan` on large tables (indicates missing index).
- `Bitmap Heap Scan` with `Bitmap Index Scan` (good).
- `Index Scan` / `Index Only Scan` (optimal).
"""

    @classmethod
    def _explain_rest_api_design(cls) -> str:
        return """### 🌐 Enterprise RESTful API Design Standards

A robust REST API follows consistent resource naming, HTTP semantics, and clear status codes.

---

### 1. HTTP Methods & Idempotency

| Method | CRUD Action | Idempotent? | Safe? | Typical Response Code |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | Read resource | Yes | Yes | `200 OK` |
| `POST` | Create resource | No | No | `201 Created` |
| `PUT` | Full replacement | Yes | No | `200 OK` / `204 No Content` |
| `PATCH` | Partial update | No | No | `200 OK` |
| `DELETE` | Remove resource | Yes | No | `204 No Content` |

---

### 2. URL Best Practices:
- Use plural nouns for resources: `/api/v1/jobs/`, `/api/v1/applications/`.
- Avoid verbs in URIs (don't use `/getJobs` or `/deleteApplication`).
- Nest child resources logically: `/api/v1/jobs/{job_id}/applicants/`.
"""

    @classmethod
    def _explain_docker(cls) -> str:
        return """### 🐳 Docker & Containerization for Django Enterprise Applications

Docker isolates applications into portable containers bundling runtime, code, system libraries, and dependencies.

---

### Production Dockerfile for Django:
```dockerfile
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential \\
    libpq-dev \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "config.wsgi:application"]
```
"""

    @classmethod
    def _explain_git_workflows(cls) -> str:
        return """### 🌿 Git Branching Workflows & Merge vs Rebase

---

### 1. Merge vs Rebase:
- **`git merge feature`**: Preserves full historical branch geometry and creates a merge commit. Safe for public shared branches.
- **`git rebase main`**: Re-applies your feature commits on top of `main`, creating a linear commit history. **Never rebase a public shared branch.**

```bash
# Clean feature branch update:
git checkout feature/ai-workspace
git fetch origin
git rebase origin/main
# Fix conflicts if any, then git rebase --continue
```
"""

    @classmethod
    def _explain_resume_optimization(cls) -> str:
        return """### 📄 10 Rules for an ATS-Proof Technical Resume

1. **Clean Single-Column Layout**: Multi-column and graphic-heavy resumes confuse ATS parsers (Workday, Greenhouse, Taleo).
2. **Standard Section Headers**: Use standard labels: `Work Experience`, `Technical Skills`, `Education`, `Projects`.
3. **Quantified Impact (Google XYZ Formula)**: *"Accomplished [X], as measured by [Y], by doing [Z]"*. (e.g. *"Reduced API latency by 42% by indexing PostgreSQL queries and introducing Redis caching"*).
4. **Keyword Alignment**: Explicitly list canonical skills (Python, Django, React, Docker, PostgreSQL) matching target vacancy descriptions.
5. **Clear Date Formatting**: Use standard `Month Year - Month Year` (e.g. `Jun 2024 - Present`).
6. **Live Project Links**: Include verifiable GitHub repositories and hosted live application URLs.
7. **File Format**: Submit PDF exported from clean text (ensure text is selectable, not a flattened image).
8. **Consistent Verb Tenses**: Past tense for previous roles, present tense for current active positions.
9. **No Fluff Summaries**: Focus on technical domain strengths and specific accomplishments.
10. **Test with HireNexa AI**: Upload your resume to `/resume-analyzer/` for instant skill overlap scoring and gap analysis!
"""

    @classmethod
    def _generic_coding_framework(cls, user_message: str) -> str:
        return f"""### 💻 HireNexa Engineering Co-Pilot: Architecture & Solution

Regarding: **"{user_message}"**

Here is the structured engineering breakdown:

---

### 1. Problem Decomposition & Architecture
When designing or debugging this component in an enterprise environment:
1. **Separation of Concerns**: Isolate data models, business validation, and presentation handlers.
2. **Input Validation**: Enforce strict boundary checks before performing database mutations.
3. **Error Handling**: Use structured `try/except` blocks with specific exception types rather than bare `except:`.

---

### 2. Production Implementation Pattern

```python
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class ServiceExecutor:
    \"\"\"Production-ready service execution pattern.\"\"\"
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {{}}

    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            logger.info("Executing pipeline with payload keys: %s", list(payload.keys()))
            
            # Step 1: Validate payload
            if not payload:
                raise ValueError("Payload cannot be empty.")
                
            # Step 2: Compute result
            result = {{"status": "SUCCESS", "processed": True, "data": payload}}
            return result
            
        except ValueError as val_err:
            logger.warning("Validation failed: %s", val_err)
            return {{"status": "ERROR", "error": str(val_err)}}
        except Exception as exc:
            logger.exception("Unexpected execution fault: %s", exc)
            return {{"status": "ERROR", "error": "Internal service error occurred."}}
```

---

### 3. Recommended Next Steps
- Would you like to write targeted unit tests (`pytest` / Django `TestCase`) for this logic?
- Or should we integrate this with a database model and REST API view?
"""
