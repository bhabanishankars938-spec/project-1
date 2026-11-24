"""
Assessments Curriculum Configuration - Ultra Pro Entrance Examination Ecosystem
Defines independent preparation tracks for MCA Entrance and MBA Entrance.
Each track contains distinct subjects, syllabus topics, subtopics, learning objectives,
and standardized 16-question, 21-minute, 5-attempt blueprints.
"""

from decimal import Decimal

CHAPTER_BLUEPRINT = {
    "question_count": 16,
    "duration_minutes": 21,
    "total_marks": Decimal("16.00"),
    "max_attempts": 5,
    "correct_marks": Decimal("1.00"),
    "negative_marking": Decimal("0.25"),
    "unanswered_marks": Decimal("0.00"),
    "difficulty_split": {
        "beginner": 4,
        "intermediate": 7,
        "advanced": 5,
    },
    "options_count": 4,
    "correct_options_count": 1,
}

ENTRANCE_TRACKS_CONFIG = [
    {
        "code": "MCA",
        "name": "MCA Entrance Preparation",
        "slug": "mca-entrance",
        "target_exams": ["NIMCET", "OJEE MCA", "CUET-PG (SCQP09)", "MAH-MCA-CET"],
        "description": "Comprehensive national and state-level MCA entrance preparation covering Higher Mathematics, Core Computer Science, Programming, and Analytical Reasoning.",
        "order": 1,
    },
    {
        "code": "MBA",
        "name": "MBA Entrance Preparation",
        "slug": "mba-entrance",
        "target_exams": ["CAT", "MAT", "CMAT", "XAT", "SNAP"],
        "description": "Premier national management entrance preparation covering Quantitative Aptitude, Data Interpretation, Verbal Ability, Reading Comprehension, and Business Awareness.",
        "order": 2,
    },
]

# Standardized MCA Entrance Subjects (16 Subjects)
MCA_SUBJECTS = [
    {
        "name": "Mathematics",
        "slug": "mathematics",
        "icon": "calculator",
        "category": "MATHEMATICS",
        "description": "Higher algebra, calculus, coordinate geometry, probability, matrices, and vectors tested in NIMCET and OJEE.",
        "topics": [
            "Sets and Relations", "Functions", "Matrices and Determinants", "Probability",
            "Permutations and Combinations", "Sequences and Series",
            "Limits, Continuity and Differentiation", "Integration", "Coordinate Geometry",
            "Vectors and 3D Geometry", "Complex Numbers", "Trigonometry",
            "Statistics and Mean-Variance", "Linear Equations and Quadratics", "Binomial Theorem"
        ],
    },
    {
        "name": "Logical Reasoning",
        "slug": "logical-reasoning",
        "icon": "brain-circuit",
        "category": "APTITUDE",
        "description": "Pattern recognition, sequence analysis, syllogisms, blood relations, and spatial reasoning.",
        "topics": [
            "Number and Letter Series", "Coding-Decoding", "Blood Relations", "Direction Sense",
            "Seating Arrangement", "Syllogisms", "Data Sufficiency", "Venn Diagrams",
            "Puzzles", "Clocks and Calendars", "Non-verbal Pattern Reasoning"
        ],
    },
    {
        "name": "Computer Awareness",
        "slug": "computer-awareness",
        "icon": "cpu",
        "category": "CORE_CS",
        "description": "Computer hardware, binary arithmetic, data representation, input/output peripherals, and system basics.",
        "topics": [
            "Number Systems and Conversions", "Boolean Algebra and Logic Gates", "Computer Organization",
            "Operating System Basics", "Networking Basics", "Internet and Security Basics",
            "MS Office and Software Basics", "Memory and Storage"
        ],
    },
    {
        "name": "Computer Organization and Architecture",
        "slug": "computer-organization-and-architecture",
        "icon": "layers",
        "category": "CORE_CS",
        "description": "ALU design, control unit architectures (hardwired vs microprogrammed), memory hierarchy, cache mapping, and instruction pipelining.",
        "topics": [
            "Number Representation", "Instruction Sets", "Addressing Modes", "Pipelining",
            "I/O and Interrupts", "Memory Organization", "Cache Memory", "CPU Architecture", "Control Unit"
        ],
    },
    {
        "name": "C Programming",
        "slug": "c-programming",
        "icon": "code",
        "category": "PROGRAMMING",
        "description": "Low-level system programming, pointers, pointer arithmetic, memory management, preprocessors, and structs in C.",
        "topics": [
            "Data Types and Operators", "Control Flow", "Functions and Recursion", "Arrays and Strings",
            "Pointers and Pointer Arithmetic", "Dynamic Memory Allocation", "Structures and Unions",
            "Storage Classes and Scope", "Preprocessor", "Bitwise Operators", "File Handling"
        ],
    },
    {
        "name": "C++",
        "slug": "cpp-programming",
        "icon": "file-code",
        "category": "PROGRAMMING",
        "description": "Object-oriented design in C++, class templates, Standard Template Library (STL), operator overloading, and inheritance.",
        "topics": [
            "C++ Fundamentals and I/O", "Classes and Objects", "Constructors and Destructors",
            "Inheritance and Polymorphism", "Virtual Functions and Abstract Classes",
            "Operator Overloading", "Templates and Generics", "STL Containers and Iterators",
            "Exception Handling in C++", "File Streams and Memory Management"
        ],
    },
    {
        "name": "Python Programming",
        "slug": "python-programming",
        "icon": "file-code",
        "category": "PROGRAMMING",
        "description": "Python syntax, mutable vs immutable data types, functional programming, OOP, exception handling, and standard library.",
        "topics": [
            "Python Fundamentals", "Variables and Data Types", "Operators", "Conditional Statements",
            "Loops", "Functions", "Strings", "Lists and Tuples", "Dictionaries and Sets",
            "Object-Oriented Programming", "Exception Handling", "File Handling"
        ],
    },
    {
        "name": "Java",
        "slug": "java-programming",
        "icon": "coffee",
        "category": "PROGRAMMING",
        "description": "JVM architecture, bytecode, OOP principles, Java Collections Framework, multithreading, and exception propagation.",
        "topics": [
            "Java Basics and JVM Architecture", "Classes, Objects and Encapsulation",
            "Inheritance and Interface Design", "Polymorphism and Method Overriding",
            "Java Collections Framework", "Multithreading and Concurrency",
            "Exception Handling and Assertions", "Java Generics and Lambda Expressions",
            "File IO and Serialization"
        ],
    },
    {
        "name": "DBMS",
        "slug": "dbms",
        "icon": "database",
        "category": "CORE_CS",
        "description": "Relational algebra, ER modeling, functional dependencies, 1NF-BCNF normalization, SQL queries, transactions, and ACID properties.",
        "topics": [
            "Database Fundamentals", "ER Model and Keys", "Relational Algebra", "Normalization and Functional Dependencies",
            "SQL Queries and Aggregations", "Joins and Subqueries", "Transactions and ACID",
            "Concurrency and Deadlocks", "Indexing and B-Trees"
        ],
    },
    {
        "name": "Data Structures and Algorithms",
        "slug": "data-structures-and-algorithms",
        "icon": "git-branch",
        "category": "CORE_CS",
        "description": "Linear/non-linear data structures, binary search trees, heaps, graph traversals (BFS/DFS), sorting, and asymptotic complexity.",
        "topics": [
            "Arrays and Linked Lists", "Stacks and Queues", "Trees and BST", "Heaps",
            "Graphs", "Hashing", "Sorting and Searching", "Complexity Analysis",
            "Greedy and Dynamic Programming", "Divide and Conquer"
        ],
    },
    {
        "name": "Operating Systems",
        "slug": "operating-systems",
        "icon": "server",
        "category": "CORE_CS",
        "description": "Kernel architecture, process states, CPU scheduling algorithms, semaphores, deadlock avoidance (Banker's), paging, and virtual memory.",
        "topics": [
            "Process and Threads", "CPU Scheduling", "Synchronization and Semaphores",
            "Deadlocks", "Memory Management and Paging", "Virtual Memory", "File Systems and Disk Scheduling"
        ],
    },
    {
        "name": "Computer Networks",
        "slug": "computer-networks",
        "icon": "wifi",
        "category": "CORE_CS",
        "description": "OSI and TCP/IP layered architectures, IP addressing, CIDR subnetting, routing protocols, flow/congestion control, and network security.",
        "topics": [
            "Network Fundamentals", "OSI Model", "TCP/IP Model", "Network Topologies",
            "Transmission Media", "IP Addressing and Subnetting", "Routing", "Switching", "Network Security"
        ],
    },
    {
        "name": "Software Engineering",
        "slug": "software-engineering",
        "icon": "box",
        "category": "CORE_CS",
        "description": "Software life cycle models (Waterfall, Spiral, Agile), requirement engineering, UML diagrams, architectural patterns, and testing techniques.",
        "topics": [
            "SDLC Models and Agile Methodology", "Software Requirements and SRS",
            "Software Design and Architectural Patterns", "UML Modeling and Class Diagrams",
            "Software Testing and Quality Assurance", "Software Maintenance and Refactoring"
        ],
    },
    {
        "name": "Discrete Mathematics",
        "slug": "discrete-mathematics",
        "icon": "binary",
        "category": "MATHEMATICS",
        "description": "Mathematical induction, set theory, relations, partially ordered sets, lattices, propositional logic, and combinatorics.",
        "topics": [
            "Propositional and Predicate Logic", "Set Theory and Relations", "Functions and Bijection",
            "Combinatorics and Counting Principles", "Recurrence Relations", "Graph Theory and Trees",
            "Boolean Algebra and Lattices"
        ],
    },
    {
        "name": "Theory of Computation",
        "slug": "theory-of-computation",
        "icon": "git-pull-request",
        "category": "CORE_CS",
        "description": "Finite automata (DFA/NFA), regular expressions, context-free grammars, pushdown automata, Turing machines, and decidability.",
        "topics": [
            "Finite Automata and Regular Languages", "DFA and NFA Equivalence",
            "Context-Free Grammars and Pushdown Automata", "Turing Machines and Decidability",
            "Chomsky Hierarchy and Pumping Lemma", "P vs NP and Computational Complexity"
        ],
    },
    {
        "name": "General English",
        "slug": "general-english",
        "icon": "book-open",
        "category": "GENERAL_ENGLISH",
        "description": "English grammar, sentence correction, reading comprehension, synonyms, antonyms, idioms, and verbal aptitude.",
        "topics": [
            "Error Spotting", "Sentence Completion", "Synonyms and Antonyms",
            "Reading Comprehension", "Para-jumbles", "Idioms and Phrases"
        ],
    },
]

# Standardized MBA Entrance Subjects (8 Subjects)
MBA_SUBJECTS = [
    {
        "name": "Quantitative Aptitude",
        "slug": "quantitative-aptitude",
        "icon": "percent",
        "category": "APTITUDE",
        "description": "Arithmetic, commercial mathematics, algebra, number system, geometry, and modern math tested in CAT, XAT, and MAT.",
        "topics": [
            "Percentages", "Profit, Loss and Discount", "Ratio and Proportion",
            "Time, Speed and Distance", "Time and Work", "Simple and Compound Interest",
            "Number System", "Algebra", "Geometry and Mensuration",
            "Permutation, Combination and Probability", "Averages, Mixtures and Alligations"
        ],
    },
    {
        "name": "Logical Reasoning",
        "slug": "logical-reasoning-mba",
        "icon": "brain-circuit",
        "category": "APTITUDE",
        "description": "Linear and matrix arrangements, family trees, direction tests, syllogisms, and sequence deduction for management entrances.",
        "topics": [
            "Linear and Circular Arrangements", "Matrix and Complex Puzzles", "Family Trees and Blood Relations",
            "Direction and Distance Sense", "Syllogistic Reasoning", "Coding, Decoding and Series",
            "Clocks and Calendars"
        ],
    },
    {
        "name": "Data Interpretation",
        "slug": "data-interpretation",
        "icon": "bar-chart-2",
        "category": "APTITUDE",
        "description": "Complex tables, stacked bar charts, multi-line graphs, pie charts, caselets, and radar data analytics.",
        "topics": [
            "Tables", "Bar and Line Graphs", "Pie Charts", "Caselets",
            "Mixed Charts and Multi-Graph Analytics", "Data Sufficiency in DI"
        ],
    },
    {
        "name": "Verbal Ability",
        "slug": "verbal-ability",
        "icon": "book",
        "category": "GENERAL_ENGLISH",
        "description": "Paragraph jumbles, summary questions, sentence completion, critical grammar, and contextual vocabulary.",
        "topics": [
            "Para-jumbles", "Para-summary", "Sentence Correction",
            "Odd-one-out", "Vocabulary in Context", "Grammar and Usage"
        ],
    },
    {
        "name": "Reading Comprehension",
        "slug": "reading-comprehension",
        "icon": "book-open",
        "category": "GENERAL_ENGLISH",
        "description": "Long-form passage analysis, inference questions, author's tone, central idea extraction, and critical reading.",
        "topics": [
            "Inference and Central Idea", "Tone and Attitude of Author",
            "Direct Factual and Detail-Oriented Questions", "Philosophy and Sociology Passages",
            "Business and Economics Passages", "Science and Technology Passages"
        ],
    },
    {
        "name": "General Awareness",
        "slug": "general-awareness",
        "icon": "globe",
        "category": "MANAGEMENT",
        "description": "National polity, constitutional landmarks, world geography, history, and scientific advancements.",
        "topics": [
            "Indian Constitution and Polity", "Geography and Environment",
            "National and World History", "Science and Everyday Technology",
            "Prominent National and International Honors"
        ],
    },
    {
        "name": "Business Awareness",
        "slug": "business-awareness",
        "icon": "briefcase",
        "category": "MANAGEMENT",
        "description": "Corporate mergers, corporate governance, fiscal policies, banking institutions, global brands, CEOs, and market economics.",
        "topics": [
            "Business and Economy Basics", "Banking and Financial Institutions",
            "Corporate Mergers and Acquisitions", "Prominent Brands, CEOs and Taglines",
            "Fiscal and Monetary Policy Concepts"
        ],
    },
    {
        "name": "Analytical Reasoning",
        "slug": "analytical-reasoning",
        "icon": "trending-up",
        "category": "APTITUDE",
        "description": "Critical reasoning, assumptions, course of action, cause and effect, and strong vs weak arguments for executive evaluation.",
        "topics": [
            "Statement and Assumptions", "Statement and Conclusions", "Cause and Effect Analysis",
            "Strong and Weak Arguments", "Course of Action and Decision Making",
            "Critical Reasoning and Argument Evaluation"
        ],
    },
]

CURRICULUM_DATA = [
    {
        "stream": "MCA Entrance",
        "slug": "mca-entrance",
        "code": "MCA",
        "target_exams": ["NIMCET", "OJEE MCA", "CUET-PG (SCQP09)", "MAH-MCA-CET"],
        "description": "National & State MCA Entrance preparation (NIMCET, OJEE, CUET-PG SCQP09, MAH-MCA-CET).",
        "order": 1,
        "subjects": MCA_SUBJECTS,
    },
    {
        "stream": "MBA Entrance",
        "slug": "mba-entrance",
        "code": "MBA",
        "target_exams": ["CAT", "MAT", "CMAT", "XAT", "SNAP"],
        "description": "Management entrance examinations (CAT, XAT, MAT, CMAT, SNAP).",
        "order": 2,
        "subjects": MBA_SUBJECTS,
    },
]

FULL_MOCK_TESTS_CONFIG = [
    {
        "title": "NIMCET MCA Entrance All-India Mock Test 2024",
        "slug": "nimcet-mca-entrance-all-india-mock-test-2024",
        "stream_slug": "mca-entrance",
        "target_entrance_exam": "NIMCET",
        "is_entrance_mock": True,
        "category": "PLACEMENT_MOCK",
        "description": "National Level NIMCET Mock Test: Mathematics (6 Qs), Logical Reasoning (5 Qs), Computer Awareness (3 Qs), General English (2 Qs).",
        "blueprint": [
            ("mathematics", 6),
            ("logical-reasoning", 5),
            ("computer-awareness", 3),
            ("general-english", 2),
        ],
    },
    {
        "title": "OJEE MCA Entrance Grand Practice Test",
        "slug": "ojee-mca-entrance-grand-practice-test",
        "stream_slug": "mca-entrance",
        "target_entrance_exam": "OJEE",
        "is_entrance_mock": True,
        "category": "MOCK_FINAL",
        "description": "State Level Odisha MCA Mock Test: Mathematics (6 Qs), Computer Fundamentals (6 Qs), Logical Reasoning (4 Qs).",
        "blueprint": [
            ("mathematics", 6),
            ("computer-awareness", 6),
            ("logical-reasoning", 4),
        ],
    },
    {
        "title": "CUET-PG (SCQP09) Computer Science Diagnostic Exam",
        "slug": "cuet-pg-scqp09-computer-science-diagnostic-exam",
        "stream_slug": "mca-entrance",
        "target_entrance_exam": "CUET-PG",
        "is_entrance_mock": True,
        "category": "WEEKLY",
        "description": "Central Universities Entrance Mock: Data Structures (5 Qs), DBMS (4 Qs), Operating Systems (4 Qs), Computer Networks (3 Qs).",
        "blueprint": [
            ("data-structures-and-algorithms", 5),
            ("dbms", 4),
            ("operating-systems", 4),
            ("computer-networks", 3),
        ],
    },
    {
        "title": "CAT Management All-India Grand Mock Test",
        "slug": "cat-management-all-india-grand-mock-test",
        "stream_slug": "mba-entrance",
        "target_entrance_exam": "CAT",
        "is_entrance_mock": True,
        "category": "MOCK_FINAL",
        "description": "Premier National Management Entrance Mock: Quantitative Aptitude (5 Qs), Data Interpretation (4 Qs), Verbal Ability (4 Qs), Reading Comprehension (3 Qs).",
        "blueprint": [
            ("quantitative-aptitude", 5),
            ("data-interpretation", 4),
            ("verbal-ability", 4),
            ("reading-comprehension", 3),
        ],
    },
    {
        "title": "MAT / CMAT Comprehensive Diagnostic Mock",
        "slug": "mat-cmat-comprehensive-diagnostic-mock",
        "stream_slug": "mba-entrance",
        "target_entrance_exam": "CMAT/MAT",
        "is_entrance_mock": True,
        "category": "WEEKLY",
        "description": "Comprehensive Management Entrance Drill: Logical Reasoning (5 Qs), Quant (4 Qs), General Awareness (4 Qs), Business Awareness (3 Qs).",
        "blueprint": [
            ("logical-reasoning-mba", 5),
            ("quantitative-aptitude", 4),
            ("general-awareness", 4),
            ("business-awareness", 3),
        ],
    },
]
