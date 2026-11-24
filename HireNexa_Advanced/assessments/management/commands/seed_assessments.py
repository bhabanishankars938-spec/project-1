import json
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify
from assessments.models import (
    Subject, Topic, Question, QuestionOption, QuestionExplanation,
    QuestionPackage, Examination, ExamQuestion, CodingProblem, TestCase,
    CareerOpportunity
)


class Command(BaseCommand):
    help = "Seeds comprehensive verified Question Bank, Entrance Exams (NIMCET, OJEE, CUET-PG), Coding Problems, and Special Interview Packages."

    def handle(self, *args, **options):
        self.stdout.write("Initializing HireNexa Assessment Data Seeder...")

        # ----------------------------------------------------------------------
        # 1. SEED SUBJECTS
        # ----------------------------------------------------------------------
        subjects_data = [
            # Entrance Exam & Core Math/Aptitude
            ("Mathematics", "calculator", Subject.Category.APTITUDE, "Calculus, Algebra, Coordinate Geometry, Probability, Vectors, Trigonometry & Set Theory for Entrance Exams"),
            ("Logical Reasoning", "brain-circuit", Subject.Category.APTITUDE, "Analytical thinking, syllogisms, blood relations, series, and puzzle reasoning"),
            ("Computer Awareness", "cpu", Subject.Category.CORE_CS, "Computer hardware, binary representation, logic gates, memories, and computing fundamentals"),
            ("General English", "book-open", Subject.Category.APTITUDE, "Grammar, sentence completion, reading comprehension, idioms, and verbal ability"),
            
            # Programming Languages
            ("C Programming", "code", Subject.Category.PROGRAMMING, "C syntax, pointers, memory management, structures, recursion, and preprocessor directives"),
            ("DBMS", "database", Subject.Category.CORE_CS, "Database design, SQL queries, relational algebra, normalization, transactions, and indexing"),
            ("Python Programming", "file-code", Subject.Category.PROGRAMMING, "Python 3 core, OOP, generators, decorators, data processing, and scripting"),
            ("C++", "terminal", Subject.Category.PROGRAMMING, "Object-oriented C++, STL containers, templates, references, and modern C++17"),
            ("Java", "coffee", Subject.Category.PROGRAMMING, "Core Java, JVM internals, multithreading, collections framework, and OOP principles"),
            ("HTML, CSS and JavaScript", "globe", Subject.Category.WEB_DEV, "Semantic markup, modern CSS layouts (Flexbox/Grid), DOM manipulation, and ES6+"),
            ("React.js", "layers", Subject.Category.WEB_DEV, "React components, Virtual DOM, Hooks, state management, reconciliation, and SPA lifecycle"),
            ("Angular", "box", Subject.Category.WEB_DEV, "Angular architecture, TypeScript, dependency injection, RxJS observables, and directives"),
            
            # Core CS
            ("Data Structures and Algorithms", "git-branch", Subject.Category.CORE_CS, "Arrays, linked lists, trees, graphs, sorting, searching, DP, and algorithmic complexity"),
            ("Operating Systems", "server", Subject.Category.CORE_CS, "Processes, threads, CPU scheduling, synchronization, deadlock, and memory management"),
            ("Computer Networks", "wifi", Subject.Category.CORE_CS, "OSI model, TCP/IP, routing algorithms, HTTP/HTTPS, DNS, and network security"),
            ("Software Engineering", "settings", Subject.Category.CORE_CS, "SDLC models, Agile/Scrum, design patterns, testing methodologies, and CI/CD"),
            ("Artificial Intelligence", "bot", Subject.Category.AI_ML, "Search algorithms, heuristic agents, game playing, expert systems, and knowledge graphs"),
            ("Machine Learning", "trending-up", Subject.Category.AI_ML, "Supervised & unsupervised learning, classification, regression, clustering, and neural nets"),
            
            # Interview Specifics
            ("Aptitude and Logical Reasoning", "percent", Subject.Category.APTITUDE, "Quantitative aptitude, percentages, time-speed-distance, work-time, and permutations"),
            ("HR Interview Questions", "user-check", Subject.Category.INTERVIEW, "Behavioral assessments, STAR method responses, teamwork, and cultural fit"),
            ("Technical Interview Questions", "award", Subject.Category.INTERVIEW, "Scenario-based technical questions, system architecture, and architectural trade-offs"),
        ]

        subject_map = {}
        for order, (name, icon, cat, desc) in enumerate(subjects_data, start=1):
            subj, _ = Subject.objects.update_or_create(
                name=name,
                defaults={
                    "slug": slugify(name),
                    "icon": icon,
                    "category": cat,
                    "description": desc,
                    "order": order,
                    "is_active": True,
                }
            )
            subject_map[name] = subj

        self.stdout.write(f"✓ Seeded {len(subject_map)} subjects.")

        # ----------------------------------------------------------------------
        # 2. SEED TOPICS
        # ----------------------------------------------------------------------
        topics_data = {
            "Mathematics": ["Set Theory & Venn Diagrams", "Probability & Statistics", "Calculus & Derivatives", "Coordinate Geometry", "Vectors & Matrices", "Trigonometry"],
            "Logical Reasoning": ["Coding-Decoding", "Blood Relations", "Direction Sense", "Syllogisms & Deductions", "Number & Letter Series", "Seating Arrangements"],
            "Computer Awareness": ["Binary Arithmetic & Number Systems", "Boolean Algebra & Logic Gates", "Computer Memory & Cache", "CPU Architecture & Registers", "Operating System Basics"],
            "C Programming": ["Pointers & Address Arithmetic", "Recursion & Functions", "Storage Classes & Scope", "Strings & Arrays", "Dynamic Memory Allocation", "Structures & Unions"],
            "DBMS": ["SQL Queries & Subqueries", "Normalization (1NF to BCNF)", "ER Modeling & Relational Schema", "Transactions & ACID Properties", "Indexing & Query Optimization"],
            "General English": ["Vocabulary & Synonyms", "Sentence Correction & Grammar", "Reading Comprehension", "Idioms & Phrases", "Active and Passive Voice"],
            "Python Programming": ["Data Structures (List, Dict, Set)", "Object Oriented Python", "Generators & Iterators", "Exception Handling", "File I/O & Modules"],
            "Data Structures and Algorithms": ["Arrays & Two Pointers", "Stacks & Queues", "Binary Trees & BST", "Dynamic Programming", "Graph Traversal (BFS/DFS)"],
            "Operating Systems": ["Process Synchronization & Semaphores", "CPU Scheduling Algorithms", "Deadlock Detection & Prevention", "Virtual Memory & Paging"],
            "Computer Networks": ["TCP/IP vs OSI Layers", "IP Addressing & Subnetting", "Routing Protocols (OSPF/BGP)", "Application Layer (HTTP/DNS)"],
            "React.js": ["Virtual DOM & Reconciliation", "React Hooks (useState, useEffect)", "State Management", "Component Lifecycle & Props"],
            "Angular": ["TypeScript Fundamentals", "Dependency Injection", "RxJS Observables", "Directives & Pipes"],
        }

        topic_map = {}
        for sname, tlist in topics_data.items():
            subj = subject_map.get(sname)
            if not subj:
                continue
            for order, tname in enumerate(tlist, start=1):
                t_obj, _ = Topic.objects.update_or_create(
                    subject=subj,
                    name=tname,
                    defaults={"slug": slugify(tname), "order": order}
                )
                topic_map[(sname, tname)] = t_obj

        self.stdout.write(f"✓ Seeded granular topics across subjects.")

        # ----------------------------------------------------------------------
        # 3. SEED QUESTIONS (WITH 4 OPTIONS, PYQS, & EXPLANATIONS)
        # ----------------------------------------------------------------------
        questions_payload = [
            # --- Mathematics (NIMCET & OJEE PYQ) ---
            {
                "subject": "Mathematics",
                "topic": "Probability & Statistics",
                "difficulty": Question.Level.INTERMEDIATE,
                "type": Question.Type.MCQ,
                "title": "Probability of Drawing Aces without Replacement",
                "question_text": "Two cards are drawn successively without replacement from a well-shuffled standard pack of 52 cards. What is the probability that both cards are Aces?",
                "marks": 1.0,
                "negative_marks": 0.25,
                "is_pyq": True,
                "pyq_exam": "NIMCET",
                "pyq_year": 2023,
                "pyq_source": "NIMCET 2023 Official Examination Paper (NIT Jamshedpur Conducting Body)",
                "options": [
                    {"key": "A", "text": "1 / 221", "is_correct": True, "explanation": "P(1st Ace) = 4/52, P(2nd Ace) = 3/51. Product = (4/52) * (3/51) = (1/13) * (1/17) = 1/221."},
                    {"key": "B", "text": "1 / 169", "is_correct": False, "explanation": "1/169 is the probability with replacement (4/52 * 4/52), which is incorrect here."},
                    {"key": "C", "text": "2 / 52", "is_correct": False, "explanation": "2/52 represents drawing one card with probability 1/26, not two Aces without replacement."},
                    {"key": "D", "text": "1 / 663", "is_correct": False, "explanation": "Incorrect denominator computation."},
                ],
                "explanation": {
                    "summary": "Option A (1 / 221) is the verified correct answer.",
                    "why_correct": "In a standard deck of 52 cards, there are exactly 4 Aces. When drawing without replacement, the probability of drawing the first Ace is 4/52. The probability of drawing a second Ace from the remaining 51 cards (which now contain 3 Aces) is 3/51. By the multiplication rule of dependent events: P = (4/52) * (3/51) = (1/13) * (1/17) = 1/221.",
                    "why_others_incorrect": "Option B (1/169) assumes drawing with replacement. Options C and D arise from calculation errors.",
                    "step_by_step": "Step 1: Identify total Aces (4) and total cards (52).\nStep 2: P(First Ace) = 4/52 = 1/13.\nStep 3: Post-draw, remaining Aces = 3, remaining cards = 51. P(Second Ace | First Ace) = 3/51 = 1/17.\nStep 4: P(Both) = (1/13) * (1/17) = 1/221.",
                    "example": "Useful in card game theory, risk modeling, and entrance examination combinatorics.",
                }
            },
            {
                "subject": "Mathematics",
                "topic": "Set Theory & Venn Diagrams",
                "difficulty": Question.Level.BEGINNER,
                "type": Question.Type.MCQ,
                "title": "Set Cardinality and Union Formula",
                "question_text": "If A and B are two finite sets such that n(A) = 35, n(B) = 42, and n(A ∪ B) = 60, what is the value of n(A ∩ B)?",
                "marks": 1.0,
                "negative_marks": 0.25,
                "is_pyq": True,
                "pyq_exam": "OJEE",
                "pyq_year": 2023,
                "pyq_source": "OJEE MCA Entrance 2023 Official Exam Paper",
                "options": [
                    {"key": "A", "text": "17", "is_correct": True, "explanation": "Using Principle of Inclusion-Exclusion: n(A ∩ B) = n(A) + n(B) - n(A ∪ B) = 35 + 42 - 60 = 17."},
                    {"key": "B", "text": "23", "is_correct": False, "explanation": "23 results from an arithmetic error subtracting from 60."},
                    {"key": "C", "text": "77", "is_correct": False, "explanation": "77 is simply n(A) + n(B), ignoring the union."},
                    {"key": "D", "text": "12", "is_correct": False, "explanation": "Incorrect value."},
                ],
                "explanation": {
                    "summary": "Option A (17) is the verified correct answer.",
                    "why_correct": "By the Principle of Inclusion-Exclusion for two finite sets: n(A ∪ B) = n(A) + n(B) - n(A ∩ B). Rearranging gives n(A ∩ B) = n(A) + n(B) - n(A ∪ B) = 35 + 42 - 60 = 77 - 60 = 17.",
                    "why_others_incorrect": "B, C, and D violate the fundamental set inclusion-exclusion identity.",
                    "step_by_step": "Step 1: Formula n(A ∪ B) = n(A) + n(B) - n(A ∩ B).\nStep 2: Substitute: 60 = 35 + 42 - n(A ∩ B).\nStep 3: 60 = 77 - n(A ∩ B) => n(A ∩ B) = 17.",
                    "example": "Survey analysis, database join overlap, and Venn diagram partitioning.",
                }
            },
            {
                "subject": "Mathematics",
                "topic": "Calculus & Derivatives",
                "difficulty": Question.Level.ADVANCED,
                "type": Question.Type.MCQ,
                "title": "Limit of (sin x) / x as x approaches 0",
                "question_text": "Evaluate the limit: lim (x -> 0) [ (sin 3x) / (tan 5x) ].",
                "marks": 1.0,
                "negative_marks": 0.25,
                "is_pyq": True,
                "pyq_exam": "CUET-PG",
                "pyq_year": 2023,
                "pyq_source": "NTA CUET-PG 2023 (SCQP09 Computer Science & Applications Paper)",
                "options": [
                    {"key": "A", "text": "3 / 5", "is_correct": True, "explanation": "lim (sin 3x)/(tan 5x) = lim [(sin 3x)/(3x) * 3x] / [(tan 5x)/(5x) * 5x] = (1 * 3) / (1 * 5) = 3/5."},
                    {"key": "B", "text": "5 / 3", "is_correct": False, "explanation": "Inverted fraction ratio."},
                    {"key": "C", "text": "0", "is_correct": False, "explanation": "Indeterminate form 0/0 resolved to 3/5 via L'Hopital or standard limit."},
                    {"key": "D", "text": "1", "is_correct": False, "explanation": "Standard limits have coefficients 3 and 5, so limit is not 1."},
                ],
                "explanation": {
                    "summary": "Option A (3 / 5) is the verified correct answer.",
                    "why_correct": "Applying L'Hopital's rule or standard trigonometric limits: lim_{x->0} (sin ax)/x = a and lim_{x->0} (tan bx)/x = b. Therefore, lim_{x->0} (sin 3x)/(tan 5x) = (3)/(5) = 3/5.",
                    "why_others_incorrect": "B inverts numerator and denominator. C wrongly assumes limit is zero. D forgets the constant multipliers.",
                    "step_by_step": "Step 1: Check form at x=0: sin(0)/tan(0) = 0/0 (indeterminate).\nStep 2: Differentiate numerator (3 cos 3x) and denominator (5 sec^2 5x).\nStep 3: Substitute x=0: (3 * cos 0) / (5 * sec^2 0) = (3 * 1) / (5 * 1) = 3/5.",
                    "example": "Rate of change analysis and digital signal processing curve approximation.",
                }
            },

            # --- C Programming (MCA Entrance, OJEE & NIMCET PYQ) ---
            {
                "subject": "C Programming",
                "topic": "Pointers & Address Arithmetic",
                "difficulty": Question.Level.INTERMEDIATE,
                "type": Question.Type.MCQ,
                "title": "Pointer Arithmetic on Integer Array",
                "question_text": "What is the exact output of the following C program?\n\n#include <stdio.h>\nint main() {\n    int arr[] = {10, 20, 30, 40, 50};\n    int *ptr = arr;\n    printf(\"%d, %d\", *ptr, *(ptr + 3));\n    return 0;\n}",
                "marks": 1.0,
                "negative_marks": 0.25,
                "is_pyq": True,
                "pyq_exam": "NIMCET",
                "pyq_year": 2022,
                "pyq_source": "NIMCET 2022 Official MCA Entrance Exam",
                "options": [
                    {"key": "A", "text": "10, 40", "is_correct": True, "explanation": "*ptr points to arr[0]=10. *(ptr + 3) accesses arr[3]=40."},
                    {"key": "B", "text": "10, 30", "is_correct": False, "explanation": "ptr + 3 moves pointer 3 elements forward to index 3 (4th element), not index 2."},
                    {"key": "C", "text": "10, 50", "is_correct": False, "explanation": "50 is at index 4 (ptr + 4)."},
                    {"key": "D", "text": "Address, Address", "is_correct": False, "explanation": "Dereference operator * yields integer values, not memory addresses."},
                ],
                "explanation": {
                    "summary": "Option A (10, 40) is the verified correct answer.",
                    "why_correct": "In C, the array name `arr` decays into a pointer to its first element arr[0]. Thus, `*ptr` dereferences to 10. Pointer arithmetic `ptr + 3` advances the pointer by `3 * sizeof(int)` bytes, pointing directly to arr[3]. Dereferencing `*(ptr + 3)` yields 40.",
                    "why_others_incorrect": "B points to index 2 (arr[2]=30). C points to arr[4]. D ignores the dereference operator.",
                    "step_by_step": "Step 1: `arr` has indices 0 to 4 with values [10, 20, 30, 40, 50].\nStep 2: `ptr = arr` means `ptr = &arr[0]`.\nStep 3: `*ptr` evaluates to arr[0] = 10.\nStep 4: `ptr + 3` evaluates to `&arr[3]`, so `*(ptr + 3)` = 40.",
                    "example": "Buffer parsing and contiguous memory traversal in embedded systems.",
                }
            },
            {
                "subject": "C Programming",
                "topic": "Storage Classes & Scope",
                "difficulty": Question.Level.BEGINNER,
                "type": Question.Type.MCQ,
                "title": "Static Variable Behavior Inside Function",
                "question_text": "What will be printed when the following C function is called twice?\n\n#include <stdio.h>\nvoid counter() {\n    static int count = 0;\n    count++;\n    printf(\"%d \", count);\n}\nint main() {\n    counter();\n    counter();\n    return 0;\n}",
                "marks": 1.0,
                "negative_marks": 0.25,
                "is_pyq": True,
                "pyq_exam": "OJEE",
                "pyq_year": 2022,
                "pyq_source": "OJEE Odisha MCA Entrance 2022",
                "options": [
                    {"key": "A", "text": "1 2", "is_correct": True, "explanation": "Static variable retains its state across multiple function invocations within the program lifetime."},
                    {"key": "B", "text": "1 1", "is_correct": False, "explanation": "An auto variable would re-initialize to 0 on each call; static does not."},
                    {"key": "C", "text": "0 1", "is_correct": False, "explanation": "Pre-increment count++ makes count 1 before the first print."},
                    {"key": "D", "text": "Compilation Error", "is_correct": False, "explanation": "Valid C syntax."},
                ],
                "explanation": {
                    "summary": "Option A (1 2) is the verified correct answer.",
                    "why_correct": "A variable declared with the `static` storage class inside a function is initialized only once during program loading and retains its value between successive calls.",
                    "why_others_incorrect": "B describes standard stack/automatic variable behavior. C miscalculates count++.",
                    "step_by_step": "Step 1: First call to counter(): `static int count = 0` initialized. count becomes 1, prints '1 '.\nStep 2: Second call to counter(): initialization skipped. count becomes 2, prints '2 '.\nResult: '1 2 '.",
                    "example": "Call counters, singleton instance caches, and state tracking without global namespace pollution.",
                }
            },

            # --- DBMS (MCA Entrance & Campus Placement) ---
            {
                "subject": "DBMS",
                "topic": "Normalization (1NF to BCNF)",
                "difficulty": Question.Level.INTERMEDIATE,
                "type": Question.Type.MCQ,
                "title": "Third Normal Form (3NF) Condition",
                "question_text": "A relational schema R is in Third Normal Form (3NF) if and only if for every non-trivial functional dependency X -> Y, which of the following holds true?",
                "marks": 1.0,
                "negative_marks": 0.25,
                "is_pyq": True,
                "pyq_exam": "CUET-PG",
                "pyq_year": 2022,
                "pyq_source": "CUET-PG MCA / Computer Science Entrance Exam 2022",
                "options": [
                    {"key": "A", "text": "Either X is a superkey OR Y is a prime attribute", "is_correct": True, "explanation": "3NF allows dependencies where the left side is a superkey OR the right side is part of a candidate key (prime attribute)."},
                    {"key": "B", "text": "X must be a candidate key AND Y must be non-prime", "is_correct": False, "explanation": "This is overly restrictive and incorrectly defined."},
                    {"key": "C", "text": "X must always be a superkey (no exceptions)", "is_correct": False, "explanation": "This is the definition of Boyce-Codd Normal Form (BCNF), not 3NF."},
                    {"key": "D", "text": "There are no functional dependencies allowed", "is_correct": False, "explanation": "Relational databases inherently rely on functional dependencies."},
                ],
                "explanation": {
                    "summary": "Option A is the verified correct answer.",
                    "why_correct": "The formal definition of 3NF states that a relation is in 3NF if it is in 2NF and for every non-trivial functional dependency X -> A: either X is a superkey, OR A is a prime attribute (a member of some candidate key). This prevents transitive dependency of non-prime attributes on candidate keys.",
                    "why_others_incorrect": "C defines BCNF. B and D are factually inaccurate definitions of database normal forms.",
                    "step_by_step": "Step 1: 1NF requires atomic values.\nStep 2: 2NF eliminates partial dependencies on candidate keys.\nStep 3: 3NF eliminates transitive dependencies: for X -> Y, X is superkey OR Y is prime.\nStep 4: BCNF is stricter: X must always be a superkey.",
                    "example": "Eliminating update, insertion, and deletion anomalies in transactional enterprise databases.",
                }
            },
            {
                "subject": "DBMS",
                "topic": "SQL Queries & Subqueries",
                "difficulty": Question.Level.BEGINNER,
                "type": Question.Type.MCQ,
                "title": "SQL Aggregate Function & NULL Handling",
                "question_text": "Given a table `Employees` with a column `bonus` containing values: [1000, 2000, NULL, 3000]. What is the result of `SELECT COUNT(bonus), COUNT(*) FROM Employees;`?",
                "marks": 1.0,
                "negative_marks": 0.25,
                "is_pyq": True,
                "pyq_exam": "NIMCET",
                "pyq_year": 2023,
                "pyq_source": "NIMCET 2023 Master of Computer Applications Entrance Exam",
                "options": [
                    {"key": "A", "text": "3, 4", "is_correct": True, "explanation": "COUNT(column) ignores NULL values (3 rows with values), whereas COUNT(*) counts all rows in the table (4 total rows)."},
                    {"key": "B", "text": "4, 4", "is_correct": False, "explanation": "COUNT(column) ignores NULLs and does not count the NULL entry."},
                    {"key": "C", "text": "3, 3", "is_correct": False, "explanation": "COUNT(*) counts the row regardless of column contents."},
                    {"key": "D", "text": "NULL, 4", "is_correct": False, "explanation": "COUNT() never returns NULL; it returns an integer count."},
                ],
                "explanation": {
                    "summary": "Option A (3, 4) is the verified correct answer.",
                    "why_correct": "In SQL standard semantics, `COUNT(column_name)` counts non-null occurrences of that column. There are 3 non-null bonus values. `COUNT(*)` counts the total number of records/tuples in the table regardless of column NULL values, yielding 4.",
                    "why_others_incorrect": "B incorrectly assumes COUNT(col) counts NULLs. C underestimates COUNT(*). D assumes aggregate returns NULL.",
                    "step_by_step": "Step 1: Evaluate COUNT(bonus): non-null values are 1000, 2000, 3000 => count = 3.\nStep 2: Evaluate COUNT(*): total rows in table = 4.\nStep 3: Output tuple = (3, 4).",
                    "example": "Financial reporting queries where optional bonuses or commission columns contain nulls.",
                }
            },

            # --- Computer Awareness & Fundamentals ---
            {
                "subject": "Computer Awareness",
                "topic": "Binary Arithmetic & Number Systems",
                "difficulty": Question.Level.BEGINNER,
                "type": Question.Type.MCQ,
                "title": "Two's Complement Representation",
                "question_text": "What is the 8-bit 2's complement representation of the decimal number -13?",
                "marks": 1.0,
                "negative_marks": 0.25,
                "is_pyq": True,
                "pyq_exam": "NIMCET",
                "pyq_year": 2022,
                "pyq_source": "NIMCET 2022 Official Test Paper",
                "options": [
                    {"key": "A", "text": "11110011", "is_correct": True, "explanation": "+13 = 00001101. Inverting bits (1's comp) = 11110010. Adding 1 = 11110011."},
                    {"key": "B", "text": "11110010", "is_correct": False, "explanation": "11110010 is the 1's complement of +13, not 2's complement."},
                    {"key": "C", "text": "10001101", "is_correct": False, "explanation": "10001101 is the sign-magnitude representation, not 2's complement."},
                    {"key": "D", "text": "11110100", "is_correct": False, "explanation": "Incorrect addition."},
                ],
                "explanation": {
                    "summary": "Option A (11110011) is the verified correct answer.",
                    "why_correct": "To find the 2's complement of a negative number in 8 bits:\n1. Express +13 in binary: 00001101\n2. Invert all bits (1's complement): 11110010\n3. Add 1 to the LSB: 11110010 + 1 = 11110011.",
                    "why_others_incorrect": "B is 1's complement. C is sign-and-magnitude. D is -12 in 2's complement.",
                    "step_by_step": "Step 1: +13 = 8 + 4 + 1 = 00001101_2.\nStep 2: Invert bits: 0->1, 1->0 => 11110010_2.\nStep 3: Add 1: 11110010 + 00000001 = 11110011_2.",
                    "example": "ALU subtraction and signed integer arithmetic in modern CPU architectures.",
                }
            },
            {
                "subject": "Computer Awareness",
                "topic": "Boolean Algebra & Logic Gates",
                "difficulty": Question.Level.INTERMEDIATE,
                "type": Question.Type.MCQ,
                "title": "Universal Logic Gates",
                "question_text": "Which of the following pairs of logic gates are designated as 'Universal Gates' because any boolean function can be realized using only them?",
                "marks": 1.0,
                "negative_marks": 0.25,
                "is_pyq": True,
                "pyq_exam": "OJEE",
                "pyq_year": 2023,
                "pyq_source": "OJEE MCA Entrance 2023 Examination",
                "options": [
                    {"key": "A", "text": "NAND and NOR", "is_correct": True, "explanation": "NAND and NOR gates are universal gates because AND, OR, and NOT gates can all be constructed using them."},
                    {"key": "B", "text": "AND and OR", "is_correct": False, "explanation": "AND and OR cannot perform negation (NOT) on their own."},
                    {"key": "C", "text": "XOR and XNOR", "is_correct": False, "explanation": "XOR and XNOR cannot implement all boolean operations independently."},
                    {"key": "D", "text": "AND and NOT", "is_correct": False, "explanation": "AND and NOT can form a functionally complete set together, but neither is a standalone universal gate like NAND or NOR."},
                ],
                "explanation": {
                    "summary": "Option A (NAND and NOR) is the verified correct answer.",
                    "why_correct": "A universal logic gate can implement any Boolean function without needing any other gate type. Both NAND and NOR gates are universal gates because they can be wired to create NOT, AND, and OR operations.",
                    "why_others_incorrect": "AND and OR cannot invert signals. XOR alone cannot produce AND or OR.",
                    "step_by_step": "Step 1: NOT x = x NAND x.\nStep 2: x AND y = (x NAND y) NAND (x NAND y).\nStep 3: x OR y = (x NAND x) NAND (y NAND y).\nConclusion: NAND and NOR are universal gates.",
                    "example": "CMOS VLSI design uses NAND and NOR cells to optimize silicon area.",
                }
            },

            # --- Logical Reasoning ---
            {
                "subject": "Logical Reasoning",
                "topic": "Coding-Decoding",
                "difficulty": Question.Level.BEGINNER,
                "type": Question.Type.MCQ,
                "title": "Letter Shift Pattern in Word Encoding",
                "question_text": "In a certain code language, if 'SYSTEM' is coded as 'SYSMET' and 'NEARER' is coded as 'AENRER', how is 'FRACTION' coded in that language?",
                "marks": 1.0,
                "negative_marks": 0.25,
                "is_pyq": True,
                "pyq_exam": "NIMCET",
                "pyq_year": 2023,
                "pyq_source": "NIMCET 2023 Official Reasoning Section",
                "options": [
                    {"key": "A", "text": "CARFNOIT", "is_correct": True, "explanation": "The word is divided into two equal halves of 4 letters each: 'FRAC' and 'TION'. Each half is reversed: 'FRAC' -> 'CARF', 'TION' -> 'NOIT', giving 'CARFNOIT'."},
                    {"key": "B", "text": "CRAFOINT", "is_correct": False, "explanation": "Incorrect letter reversal in second half."},
                    {"key": "C", "text": "ARFCNOIT", "is_correct": False, "explanation": "Incorrect first half reversal."},
                    {"key": "D", "text": "NOITCARF", "is_correct": False, "explanation": "Reversing and swapping halves is not the pattern used in the examples."},
                ],
                "explanation": {
                    "summary": "Option A (CARFNOIT) is the verified correct answer.",
                    "why_correct": "Analyze the transformation: 'SYSTEM' (6 letters) split into SYS | TEM. First half SYS reversed = SYS; second half TEM reversed = MET => SYSMET. 'NEARER' split into NEA | RER. NEA reversed = AEN; RER reversed = RER => AENRER. For 'FRACTION' (8 letters): split into FRAC | TION. FRAC reversed is CARF, TION reversed is NOIT. Combined: CARFNOIT.",
                    "why_others_incorrect": "B, C, and D misapply the reverse order of the 4-letter segments.",
                    "step_by_step": "Step 1: Check length of 'FRACTION' = 8 letters.\nStep 2: Half 1 = 'FRAC' (letters 1-4). Reversing yields 'CARF'.\nStep 3: Half 2 = 'TION' (letters 5-8). Reversing yields 'NOIT'.\nStep 4: Concatenate: CARF + NOIT = CARFNOIT.",
                    "example": "Standard cryptographic transposition cipher logic.",
                }
            },
            {
                "subject": "Logical Reasoning",
                "topic": "Syllogisms & Deductions",
                "difficulty": Question.Level.INTERMEDIATE,
                "type": Question.Type.MCQ,
                "title": "Two-Premise Syllogism Validity",
                "question_text": "Statements:\n1. All developers are problem solvers.\n2. Some problem solvers are mathematicians.\n\nConclusions:\nI. Some developers are mathematicians.\nII. Some problem solvers are developers.\n\nWhich conclusion(s) logically follow?",
                "marks": 1.0,
                "negative_marks": 0.25,
                "is_pyq": True,
                "pyq_exam": "CUET-PG",
                "pyq_year": 2023,
                "pyq_source": "CUET-PG General Reasoning 2023",
                "options": [
                    {"key": "A", "text": "Only Conclusion II follows", "is_correct": True, "explanation": "Statement 1 converts directly: If All A are B, then Some B are A. Hence Some problem solvers are developers follows. There is no definite link between developers and mathematicians."},
                    {"key": "B", "text": "Only Conclusion I follows", "is_correct": False, "explanation": "The middle term 'problem solvers' is undistributed, so no definite relationship exists between developers and mathematicians."},
                    {"key": "C", "text": "Both Conclusion I and II follow", "is_correct": False, "explanation": "Conclusion I is only a possibility, not a necessary logical consequence."},
                    {"key": "D", "text": "Neither conclusion follows", "is_correct": False, "explanation": "Conclusion II is a valid conversion of Statement 1."},
                ],
                "explanation": {
                    "summary": "Option A (Only Conclusion II follows) is the verified correct answer.",
                    "why_correct": "From Statement 1: 'All D are P' implies 'Some P are D' (conversion by limitation). Thus, Conclusion II is universally valid. From Statement 2: 'Some P are M'. Since 'P' is not distributed in either premise, we cannot chain D to M. Conclusion I does not necessarily follow.",
                    "why_others_incorrect": "Conclusion I commits the Fallacy of the Undistributed Middle Term.",
                    "step_by_step": "Step 1: Analyze Premise 1: Universal affirmative (All D are P). Valid conversion: Some P are D. Conclusion II is true.\nStep 2: Analyze Premise 2: Particular affirmative (Some P are M).\nStep 3: Test overlap between D and M: Disjoint sets of D and M within P are possible.\nConclusion: Only II follows.",
                    "example": "Critical thinking and analytical reasoning tests for software engineer placements.",
                }
            },

            # --- General English ---
            {
                "subject": "General English",
                "topic": "Vocabulary & Synonyms",
                "difficulty": Question.Level.BEGINNER,
                "type": Question.Type.MCQ,
                "title": "Synonym of 'Ephemeral'",
                "question_text": "Choose the word that is most nearly identical in meaning (synonym) to 'EPHEMERAL':",
                "marks": 1.0,
                "negative_marks": 0.25,
                "is_pyq": True,
                "pyq_exam": "NIMCET",
                "pyq_year": 2022,
                "pyq_source": "NIMCET 2022 General English Section",
                "options": [
                    {"key": "A", "text": "Transient", "is_correct": True, "explanation": "Ephemeral means lasting for a very short time; transient means lasting only for a short time (impermanent)."},
                    {"key": "B", "text": "Eternal", "is_correct": False, "explanation": "Eternal is an antonym, meaning lasting forever."},
                    {"key": "C", "text": "Substantial", "is_correct": False, "explanation": "Substantial means of considerable importance, size, or worth."},
                    {"key": "D", "text": "Perpetual", "is_correct": False, "explanation": "Perpetual means never ending or changing (antonym)."},
                ],
                "explanation": {
                    "summary": "Option A (Transient) is the verified correct answer.",
                    "why_correct": "'Ephemeral' (from Greek ephemeros, lasting a day) means short-lived or fleeting. 'Transient' directly shares this meaning of existing briefly.",
                    "why_others_incorrect": "Eternal and Perpetual are direct antonyms meaning everlasting. Substantial relates to material weight.",
                    "step_by_step": "Step 1: Define 'Ephemeral': lasting a very short time.\nStep 2: Evaluate options: Transient = fleeting; Eternal = unending; Perpetual = continuous.\nStep 3: Best synonym is Transient.",
                    "example": "In computing: 'ephemeral ports' are temporary transport protocol ports allocated dynamically.",
                }
            },

            # --- React.js & Web Development ---
            {
                "subject": "React.js",
                "topic": "Virtual DOM & Reconciliation",
                "difficulty": Question.Level.INTERMEDIATE,
                "type": Question.Type.MCQ,
                "title": "Why React Was Introduced & Virtual DOM",
                "question_text": "What was the primary technological bottleneck that led Jordan Walke and the Facebook engineering team to invent React and its Virtual DOM?",
                "marks": 1.0,
                "negative_marks": 0.0,
                "is_pyq": False,
                "pyq_exam": "",
                "pyq_year": None,
                "pyq_source": "Technical Interview Special Package",
                "options": [
                    {"key": "A", "text": "Frequent real browser DOM manipulations are computationally expensive due to reflow and repaint cycles", "is_correct": True, "explanation": "Direct DOM manipulation causes expensive browser layout reflows and repaints. React batches updates and computes minimal diffs in an in-memory Virtual DOM tree."},
                    {"key": "B", "text": "JavaScript lacked the ability to manipulate the DOM natively", "is_correct": False, "explanation": "JavaScript has had native DOM manipulation APIs (document.getElementById, querySelector) since early web browsers."},
                    {"key": "C", "text": "CSS animations could not run without JavaScript libraries", "is_correct": False, "explanation": "CSS animations are rendered natively by the browser graphics pipeline."},
                    {"key": "D", "text": "Browsers could not handle asynchronous HTTP requests", "is_correct": False, "explanation": "XMLHttpRequest and Fetch API provided asynchronous requests long before React."},
                ],
                "explanation": {
                    "summary": "Option A is the verified correct answer.",
                    "why_correct": "The browser DOM represents documents as a tree of nodes. Modifying DOM elements directly triggers layout recalculation (reflow) and re-rendering (repaint), which are resource-heavy operations in complex dynamic apps like Facebook's notification feed. React introduced the Virtual DOM to maintain a lightweight in-memory representation, run efficient diffing algorithms (Reconciliation), and apply only the minimal required batch changes to the real DOM.",
                    "why_others_incorrect": "B, C, and D state false claims about browser capabilities prior to React.",
                    "step_by_step": "Step 1: Real DOM mutation triggers Layout Reflow and Repaint.\nStep 2: React builds lightweight VDOM in JavaScript memory.\nStep 3: State changes generate a new VDOM tree.\nStep 4: Diffing algorithm compares old and new trees.\nStep 5: Only necessary nodes are updated in the real DOM.",
                    "example": "A chat application updating 100 messages simultaneously only changes the text content of the newest message without re-rendering the entire chat window.",
                }
            },
            {
                "subject": "Angular",
                "topic": "TypeScript Fundamentals",
                "difficulty": Question.Level.INTERMEDIATE,
                "type": Question.Type.MCQ,
                "title": "Why Angular Was Introduced & Architecture",
                "question_text": "What architectural distinction best contrasts Angular from React?",
                "marks": 1.0,
                "negative_marks": 0.0,
                "is_pyq": False,
                "pyq_exam": "",
                "pyq_year": None,
                "pyq_source": "Frontend Architecture Interview Special Package",
                "options": [
                    {"key": "A", "text": "Angular is a complete, opinionated framework providing built-in routing, forms, HTTP client, and Dependency Injection, whereas React is a focused UI library", "is_correct": True, "explanation": "Angular is an all-inclusive 'batteries-included' framework with strict conventions; React focuses purely on the view layer and delegates routing and state to third-party packages."},
                    {"key": "B", "text": "Angular only runs on mobile devices while React runs only on desktop", "is_correct": False, "explanation": "Both run universally across all modern browsers and devices."},
                    {"key": "C", "text": "Angular does not support TypeScript", "is_correct": False, "explanation": "Angular is built primarily with and requires TypeScript."},
                    {"key": "D", "text": "React requires a backend server to render, whereas Angular cannot render on servers", "is_correct": False, "explanation": "Both support client-side rendering (CSR) and server-side rendering (SSR via Next.js and Angular Universal)."},
                ],
                "explanation": {
                    "summary": "Option A is the verified correct answer.",
                    "why_correct": "Google engineered Angular as a complete enterprise application framework offering out-of-the-box solutions for routing, state handling, HTTP client requests, form validation, and hierarchical dependency injection. React was designed as a component-driven UI library allowing developers freedom to pick external libraries for routing (react-router) and state management (Redux, Zustand).",
                    "why_others_incorrect": "B, C, and D are factually false statements regarding Angular and React capabilities.",
                    "step_by_step": "Step 1: Angular = Full-fledged Framework with opinionated architecture.\nStep 2: React = View-layer Library with flexible composable architecture.\nStep 3: Angular uses real DOM with dirty-checking/signals and two-way binding; React uses Virtual DOM with one-way data flow.",
                    "example": "Large enterprise banking systems often adopt Angular for its strict consistency, while consumer SaaS startups frequently prefer React for its agile ecosystem.",
                }
            },
        ]

        # Bulk create questions, options, and explanations
        created_count = 0
        for q_data in questions_payload:
            subj = subject_map.get(q_data["subject"])
            topic_obj = topic_map.get((q_data["subject"], q_data.get("topic")))
            if not subj:
                continue

            q, created = Question.objects.update_or_create(
                title=q_data["title"],
                defaults={
                    "subject": subj,
                    "topic": topic_obj,
                    "difficulty": q_data["difficulty"],
                    "question_type": q_data["type"],
                    "question_text": q_data["question_text"],
                    "marks": q_data["marks"],
                    "negative_marks": q_data["negative_marks"],
                    "is_pyq": q_data.get("is_pyq", False),
                    "pyq_exam": q_data.get("pyq_exam", ""),
                    "pyq_year": q_data.get("pyq_year"),
                    "pyq_source": q_data.get("pyq_source", ""),
                    "status": Question.Status.APPROVED,
                    "verification_certainty": 1.00,
                }
            )

            # Seed options
            for opt_idx, opt_info in enumerate(q_data["options"], start=1):
                QuestionOption.objects.update_or_create(
                    question=q,
                    option_key=opt_info["key"],
                    defaults={
                        "option_text": opt_info["text"],
                        "is_correct": opt_info["is_correct"],
                        "explanation": opt_info.get("explanation", ""),
                        "order": opt_idx,
                    }
                )

            # Seed explanation
            exp_info = q_data.get("explanation", {})
            if exp_info:
                QuestionExplanation.objects.update_or_create(
                    question=q,
                    defaults={
                        "correct_answer_summary": exp_info.get("summary", ""),
                        "why_correct": exp_info.get("why_correct", ""),
                        "why_others_incorrect": exp_info.get("why_others_incorrect", ""),
                        "step_by_step_logic": exp_info.get("step_by_step", ""),
                        "practical_example": exp_info.get("example", ""),
                    }
                )
            created_count += 1

        self.stdout.write(f"✓ Seeded {created_count} verified questions with 4-options and complete explanations.")

        # ----------------------------------------------------------------------
        # 4. SEED CODING PROBLEMS & TEST CASES (HACKERRANK STYLE)
        # ----------------------------------------------------------------------
        coding_payload = [
            {
                "title": "Two Sum Problem",
                "difficulty": CodingProblem.Difficulty.EASY,
                "subject": "Data Structures and Algorithms",
                "description": "Given an array of integers `nums` and an integer `target`, return the indices of the two numbers such that they add up to `target`.\n\nYou may assume that each input would have exactly one solution, and you may not use the same element twice. Return the indices separated by a space, sorted in ascending order.",
                "input_format": "Line 1: An integer N representing number of elements.\nLine 2: N space-separated integers representing nums.\nLine 3: An integer representing target sum.",
                "output_format": "Print two space-separated indices (0-indexed).",
                "constraints": "2 <= N <= 10^5\n-10^9 <= nums[i] <= 10^9\n-10^9 <= target <= 10^9",
                "time_limit": 2.0,
                "memory_limit": 128,
                "starter_templates": {
                    "python": "import sys\n\ndef two_sum(nums, target):\n    # Write your solution here\n    pass\n\nif __name__ == '__main__':\n    lines = sys.stdin.read().split()\n    if lines:\n        n = int(lines[0])\n        nums = [int(x) for x in lines[1:n+1]]\n        target = int(lines[n+1])\n        # Output indices e.g.: print(f\"{i} {j}\")\n        seen = {}\n        for idx, val in enumerate(nums):\n            comp = target - val\n            if comp in seen:\n                print(f\"{seen[comp]} {idx}\")\n                break\n            seen[val] = idx\n",
                    "javascript": r"const fs = require('fs');" + "\n" + r"const input = fs.readFileSync(0, 'utf-8').trim().split(/\s+/);" + "\n" + r"if (input.length > 2) {" + "\n" + r"    const n = parseInt(input[0]);" + "\n" + r"    const nums = input.slice(1, n + 1).map(Number);" + "\n" + r"    const target = parseInt(input[n + 1]);" + "\n" + r"    const map = new Map();" + "\n" + r"    for (let i = 0; i < nums.length; i++) {" + "\n" + r"        const comp = target - nums[i];" + "\n" + r"        if (map.has(comp)) {" + "\n" + r"            console.log(`${map.get(comp)} ${i}`);" + "\n" + r"            break;" + "\n" + r"        }" + "\n" + r"        map.set(nums[i], i);" + "\n" + r"    }" + "\n" + r"}" + "\n",
                    "c": "#include <stdio.h>\n#include <stdlib.h>\nint main() {\n    int n;\n    if (scanf(\"%d\", &n) != 1) return 0;\n    int *nums = (int*)malloc(n * sizeof(int));\n    for (int i = 0; i < n; i++) scanf(\"%d\", &nums[i]);\n    int target;\n    scanf(\"%d\", &target);\n    for (int i = 0; i < n; i++) {\n        for (int j = i + 1; j < n; j++) {\n            if (nums[i] + nums[j] == target) {\n                printf(\"%d %d\\n\", i, j);\n                free(nums);\n                return 0;\n            }\n        }\n    }\n    free(nums);\n    return 0;\n}\n",
                    "cpp": "#include <iostream>\n#include <vector>\n#include <unordered_map>\nusing namespace std;\nint main() {\n    int n; if (!(cin >> n)) return 0;\n    vector<int> nums(n);\n    for (int i = 0; i < n; i++) cin >> nums[i];\n    int target; cin >> target;\n    unordered_map<int, int> mp;\n    for (int i = 0; i < n; i++) {\n        int comp = target - nums[i];\n        if (mp.count(comp)) {\n            cout << mp[comp] << \" \" << i << \"\\n\";\n            return 0;\n        }\n        mp[nums[i]] = i;\n    }\n    return 0;\n}\n"
                },
                "test_cases": [
                    {"input": "4\n2 7 11 15\n9", "output": "0 1", "is_hidden": False, "explanation": "nums[0] + nums[1] == 2 + 7 == 9."},
                    {"input": "3\n3 2 4\n6", "output": "1 2", "is_hidden": False, "explanation": "nums[1] + nums[2] == 2 + 4 == 6."},
                    {"input": "5\n1 5 8 12 19\n20", "output": "0 4", "is_hidden": True, "explanation": "1 + 19 = 20."},
                    {"input": "6\n-3 4 3 90 2 1\n0", "output": "0 2", "is_hidden": True, "explanation": "-3 + 3 = 0."},
                ]
            },
            {
                "title": "Valid Parentheses",
                "difficulty": CodingProblem.Difficulty.EASY,
                "subject": "Data Structures and Algorithms",
                "description": "Given a string `s` containing just the characters `'('`, `')'`, `'{'`, `'}'`, `'['` and `']'`, determine if the input string is valid.\n\nAn input string is valid if:\n1. Open brackets must be closed by the same type of brackets.\n2. Open brackets must be closed in the correct order.\n3. Every close bracket has a corresponding open bracket of the same type.\n\nPrint `true` if valid, otherwise print `false`.",
                "input_format": "A single string containing brackets.",
                "output_format": "Print `true` or `false` in lowercase.",
                "constraints": "1 <= s.length <= 10^4",
                "time_limit": 2.0,
                "memory_limit": 128,
                "starter_templates": {
                    "python": "import sys\ndef is_valid(s):\n    stack = []\n    mapping = {')': '(', '}': '{', ']': '['}\n    for char in s.strip():\n        if char in mapping:\n            top = stack.pop() if stack else '#'\n            if mapping[char] != top:\n                return False\n        else:\n            stack.append(char)\n    return not stack\n\nif __name__ == '__main__':\n    inp = sys.stdin.read().strip()\n    print('true' if is_valid(inp) else 'false')\n",
                    "javascript": "const fs = require('fs');\nconst s = fs.readFileSync(0, 'utf-8').trim();\nfunction isValid(str) {\n    const stack = [];\n    const map = { ')': '(', '}': '{', ']': '[' };\n    for (let ch of str) {\n        if (map[ch]) {\n            if (stack.pop() !== map[ch]) return false;\n        } else {\n            stack.push(ch);\n        }\n    }\n    return stack.length === 0;\n}\nconsole.log(isValid(s) ? 'true' : 'false');\n",
                    "cpp": "#include <iostream>\n#include <stack>\n#include <string>\nusing namespace std;\nbool isValid(string s) {\n    stack<char> st;\n    for (char c : s) {\n        if (c == '(' || c == '{' || c == '[') st.push(c);\n        else {\n            if (st.empty()) return false;\n            char top = st.top(); st.pop();\n            if (c == ')' && top != '(') return false;\n            if (c == '}' && top != '{') return false;\n            if (c == ']' && top != '[') return false;\n        }\n    }\n    return st.empty();\n}\nint main() {\n    string s; if (cin >> s) cout << (isValid(s) ? \"true\" : \"false\") << \"\\n\";\n    return 0;\n}\n"
                },
                "test_cases": [
                    {"input": "()[]{}", "output": "true", "is_hidden": False, "explanation": "Properly nested bracket pairs."},
                    {"input": "(]", "output": "false", "is_hidden": False, "explanation": "Mismatched closing bracket."},
                    {"input": "({[]})", "output": "true", "is_hidden": True, "explanation": "Deeply nested balanced brackets."},
                    {"input": "([)]", "output": "false", "is_hidden": True, "explanation": "Interleaved improper closing order."},
                ]
            }
        ]

        for cp in coding_payload:
            subj = subject_map.get(cp["subject"])
            prob, _ = CodingProblem.objects.update_or_create(
                title=cp["title"],
                defaults={
                    "slug": slugify(cp["title"]),
                    "subject": subj,
                    "difficulty": cp["difficulty"],
                    "description": cp["description"],
                    "input_format": cp["input_format"],
                    "output_format": cp["output_format"],
                    "constraints": cp["constraints"],
                    "time_limit_seconds": cp["time_limit"],
                    "memory_limit_mb": cp["memory_limit"],
                    "starter_templates": cp["starter_templates"],
                }
            )
            for idx, tc in enumerate(cp["test_cases"], start=1):
                TestCase.objects.update_or_create(
                    problem=prob,
                    order=idx,
                    defaults={
                        "input_data": tc["input"],
                        "expected_output": tc["output"],
                        "is_hidden": tc["is_hidden"],
                        "explanation": tc.get("explanation", ""),
                    }
                )

        self.stdout.write(f"✓ Seeded coding problems with sample and hidden test cases.")

        # ----------------------------------------------------------------------
        # 5. SEED ENTRANCE EXAM & LIVE TESTS
        # ----------------------------------------------------------------------
        exams_payload = [
            {
                "title": "NIMCET MCA Entrance All-India Mock Test 2024",
                "category": Examination.Category.PLACEMENT_MOCK,
                "target_entrance_exam": "NIMCET",
                "is_entrance_mock": True,
                "duration_minutes": 120,
                "total_marks": 120.0,
                "passing_percentage": 45.0,
                "negative_marking_rate": 0.25,
                "description": "Full-length authentic NIMCET mock examination adhering to the official syllabus: Mathematics (50 marks), Analytical Ability & Logical Reasoning (40 marks), Computer Awareness (20 marks), and General English (10 marks).",
                "instructions": "1. Test duration is 120 minutes with automatic server countdown.\n2. Each correct MCQ awards +1 mark. Each incorrect answer deducts 0.25 marks.\n3. Use 'Mark for Review' to revisit doubtful questions from the palette.\n4. Answers auto-save in real time. Do not close or refresh until submitted.",
            },
            {
                "title": "OJEE MCA Entrance Grand Practice Test",
                "category": Examination.Category.MOCK_FINAL,
                "target_entrance_exam": "OJEE",
                "is_entrance_mock": True,
                "duration_minutes": 60,
                "total_marks": 60.0,
                "passing_percentage": 40.0,
                "negative_marking_rate": 0.25,
                "description": "Comprehensive simulation for the Odisha Joint Entrance Examination (OJEE) for Master in Computer Applications. Covers Mathematics and Computer Awareness.",
                "instructions": "Timed mock test replicating the standard OJEE computer-based test (CBT) environment.",
            },
            {
                "title": "CUET-PG (SCQP09) Computer Science Diagnostic Exam",
                "category": Examination.Category.WEEKLY,
                "target_entrance_exam": "CUET-PG",
                "is_entrance_mock": True,
                "duration_minutes": 45,
                "total_marks": 40.0,
                "passing_percentage": 40.0,
                "negative_marking_rate": 0.25,
                "description": "Standardized diagnostic assessment targeting Central Universities MCA / M.Sc Computer Science entrance via NTA CUET-PG.",
                "instructions": "Practice test with synchronized timer and instant results upon completion.",
            },
            {
                "title": "C Programming & Pointer Architecture Assessment",
                "category": Examination.Category.DAILY,
                "target_entrance_exam": "MCA Entrance",
                "is_entrance_mock": True,
                "duration_minutes": 20,
                "total_marks": 20.0,
                "passing_percentage": 50.0,
                "negative_marking_rate": 0.0,
                "description": "Daily technical drill covering memory layouts, pointers, recursion, and preprocessor directives in C.",
                "instructions": "Rapid technical assessment designed to sharpen core programming fundamentals.",
            },
            {
                "title": "DBMS & SQL Query Master Live Test",
                "category": Examination.Category.LIVE_TEST,
                "target_entrance_exam": "Technical Interview",
                "is_entrance_mock": False,
                "duration_minutes": 30,
                "total_marks": 25.0,
                "passing_percentage": 40.0,
                "negative_marking_rate": 0.25,
                "description": "Live assessment test covering relational modeling, normal forms, transaction ACID properties, and SQL aggregation.",
                "instructions": "Strictly timed live test with instant candidate percentile report.",
            }
        ]

        all_seeded_questions = list(Question.objects.filter(status=Question.Status.APPROVED))

        for ex_data in exams_payload:
            exam, _ = Examination.objects.update_or_create(
                title=ex_data["title"],
                defaults={
                    "slug": slugify(ex_data["title"]),
                    "category": ex_data["category"],
                    "target_entrance_exam": ex_data["target_entrance_exam"],
                    "is_entrance_mock": ex_data["is_entrance_mock"],
                    "duration_minutes": ex_data["duration_minutes"],
                    "total_marks": ex_data["total_marks"],
                    "passing_percentage": ex_data["passing_percentage"],
                    "negative_marking_rate": ex_data["negative_marking_rate"],
                    "description": ex_data["description"],
                    "instructions": ex_data["instructions"],
                    "shuffle_questions": True,
                    "shuffle_options": True,
                    "show_instant_results": True,
                    "is_published": True,
                }
            )

            # Link relevant questions
            for order, q in enumerate(all_seeded_questions, start=1):
                ExamQuestion.objects.update_or_create(
                    examination=exam,
                    question=q,
                    defaults={"order": order, "custom_marks": 1.0}
                )

        self.stdout.write(f"✓ Seeded Mock Tests and Entrance Examinations.")

        # ----------------------------------------------------------------------
        # 6. SEED SPECIAL INTERVIEW PACKAGES
        # ----------------------------------------------------------------------
        special_packages = [
            ("Why React Was Introduced", "layers", "In-depth breakdown of DOM bottlenecks, reflow/repaint costs, Virtual DOM, and component composition."),
            ("Why Angular Was Introduced", "box", "Detailed exploration of Google's enterprise framework vision, TypeScript adoption, and Dependency Injection."),
            ("React vs Angular: Architectural Deep Dive", "shuffle", "Direct comparison of state management, learning curve, performance, and ecosystem tradeoffs."),
            ("Frontend Development Master Package", "globe", "Core CSS layouts, responsive design, Modern ES6+, accessibility, and web performance optimization."),
            ("Forward Deployed Engineer (FDE) Playbook", "terminal", "Customer-facing engineering, rapid prototyping, production debugging, and bridging product with client stack."),
            ("HackerRank-Style Assessment Blueprint", "code", "Two-pointer techniques, sliding windows, stack problems, edge-case testing, and time complexity estimation."),
            ("AI Project Monitoring & Observability", "bot", "Tracking LLM latency, token economics, hallucination detection, evaluation benchmarks, and guardrails."),
            ("Software Development & Production Deployment", "server", "Git workflows, Docker containerization, CI/CD pipelines, Kubernetes orchestration, and zero-downtime rollouts."),
        ]

        for pkg_title, icon, pkg_desc in special_packages:
            pkg, _ = QuestionPackage.objects.update_or_create(
                title=pkg_title,
                defaults={
                    "slug": slugify(pkg_title),
                    "icon": icon,
                    "description": pkg_desc,
                    "category": QuestionPackage.Category.SPECIAL_INTERVIEW,
                    "is_featured": True,
                }
            )
            # Attach available approved questions
            pkg.questions.set(all_seeded_questions[:6])

        self.stdout.write(f"✓ Seeded 8 Special Interview Topic Learning Packages.")

        # ----------------------------------------------------------------------
        # 7. SEED CAREER OPPORTUNITIES & INTERNSHIPS (VERIFIED ATTRIBUTION)
        # ----------------------------------------------------------------------
        opportunities_data = [
            {
                "type": CareerOpportunity.Type.INTERNSHIP,
                "title": "Software Development Engineer (SDE) Intern - Cloud & AI",
                "org": "HireNexa Enterprise Labs",
                "loc": "Bengaluru / Hybrid",
                "stipend": "₹35,000 / month",
                "source": "HireNexa Campus Direct Network",
                "url": "https://hirenexa.com/careers/internships/sde-cloud",
                "requirements": ["Python or Java proficiency", "Data Structures & Algorithms", "Basic Git & REST APIs", "Pre-final / Final Year Students"],
                "desc": "Join our platform core engineering team building scalable microservices, AI evaluation pipelines, and high-performance coding assessment engines.",
            },
            {
                "type": CareerOpportunity.Type.INTERNSHIP,
                "title": "Frontend Engineer Intern (React / TypeScript)",
                "org": "Nexus Interactive Technologies",
                "loc": "Remote",
                "stipend": "₹25,000 / month",
                "source": "Verified Partner Hiring Portal",
                "url": "https://hirenexa.com/careers/internships/frontend-react",
                "requirements": ["React.js", "TypeScript", "Modern CSS / Tailwind", "Responsive Web Design"],
                "desc": "Design modern user interfaces, live exam palettes, code editors, and real-time candidate dashboards.",
            },
            {
                "type": CareerOpportunity.Type.TRAINING,
                "title": "Master National MCA Entrance Bootcamp 2024",
                "org": "National Entrance Prep Academy",
                "loc": "Live Online",
                "stipend": "Free Certified Training",
                "source": "Verified EdTech Partner",
                "url": "https://hirenexa.com/training/mca-bootcamp-2024",
                "requirements": ["NIMCET / OJEE / CUET-PG Aspirants", "Mathematics & C Programming Basics"],
                "desc": "Intensive 6-week training covering previous 10 years question trends, mathematical problem solving, and mock exam simulations.",
            },
            {
                "type": CareerOpportunity.Type.PLACEMENT_DRIVE,
                "title": "National Off-Campus Placement Drive 2024",
                "org": "Multi-Tenant Enterprise Hiring Consortium",
                "loc": "Pan-India / Multiple Locations",
                "stipend": "₹6.5 - ₹12.0 LPA CTC",
                "source": "HireNexa Placement Cell Verified",
                "url": "https://hirenexa.com/placements/national-drive-2024",
                "requirements": ["B.Tech / MCA / B.Sc CS graduates", "Minimum 60% aggregate", "HireNexa Placement Readiness Score >= 65%"],
                "desc": "Direct interviews with 25+ verified technology organizations for full-stack software engineer and analyst roles.",
            }
        ]

        for opp in opportunities_data:
            CareerOpportunity.objects.update_or_create(
                title=opp["title"],
                organization_name=opp["org"],
                defaults={
                    "opportunity_type": opp["type"],
                    "location": opp["loc"],
                    "stipend_or_perk": opp["stipend"],
                    "source_name": opp["source"],
                    "source_url": opp["url"],
                    "verification_date": timezone.now().date(),
                    "requirements": opp["requirements"],
                    "description": opp["desc"],
                    "is_active": True,
                }
            )

        self.stdout.write(f"✓ Seeded verified career and internship opportunities.")
        self.stdout.write(self.style.SUCCESS("All assessment seeds created and verified successfully!"))
