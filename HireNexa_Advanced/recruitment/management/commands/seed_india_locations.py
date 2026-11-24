import os
from django.core.management.base import BaseCommand
from django.db import transaction
from recruitment.models import Country, State, District, City, Area, PinCode, Job, Organization
from accounts.models import User


class Command(BaseCommand):
    help = "Seeds comprehensive and verified Indian location hierarchy (States, Districts, Cities, Localities) and sample jobs."

    def handle(self, *args, **options):
        self.stdout.write("Seeding India location hierarchy...")

        with transaction.atomic():
            # 1. Country: India
            country, _ = Country.objects.get_or_create(
                name="India",
                defaults={"iso2": "IN", "iso3": "IND", "phone_code": "+91"}
            )

            # 2. Complete 28 States + 8 Union Territories
            states_data = [
                ("Andhra Pradesh", "AP", State.Type.STATE),
                ("Arunachal Pradesh", "AR", State.Type.STATE),
                ("Assam", "AS", State.Type.STATE),
                ("Bihar", "BR", State.Type.STATE),
                ("Chhattisgarh", "CG", State.Type.STATE),
                ("Goa", "GA", State.Type.STATE),
                ("Gujarat", "GJ", State.Type.STATE),
                ("Haryana", "HR", State.Type.STATE),
                ("Himachal Pradesh", "HP", State.Type.STATE),
                ("Jharkhand", "JH", State.Type.STATE),
                ("Karnataka", "KA", State.Type.STATE),
                ("Kerala", "KL", State.Type.STATE),
                ("Madhya Pradesh", "MP", State.Type.STATE),
                ("Maharashtra", "MH", State.Type.STATE),
                ("Manipur", "MN", State.Type.STATE),
                ("Meghalaya", "ML", State.Type.STATE),
                ("Mizoram", "MZ", State.Type.STATE),
                ("Nagaland", "NL", State.Type.STATE),
                ("Odisha", "OD", State.Type.STATE),
                ("Punjab", "PB", State.Type.STATE),
                ("Rajasthan", "RJ", State.Type.STATE),
                ("Sikkim", "SK", State.Type.STATE),
                ("Tamil Nadu", "TN", State.Type.STATE),
                ("Telangana", "TS", State.Type.STATE),
                ("Tripura", "TR", State.Type.STATE),
                ("Uttar Pradesh", "UP", State.Type.STATE),
                ("Uttarakhand", "UK", State.Type.STATE),
                ("West Bengal", "WB", State.Type.STATE),
                # Union Territories
                ("Andaman and Nicobar Islands", "AN", State.Type.UNION_TERRITORY),
                ("Chandigarh", "CH", State.Type.UNION_TERRITORY),
                ("Dadra and Nagar Haveli and Daman and Diu", "DH", State.Type.UNION_TERRITORY),
                ("Delhi", "DL", State.Type.UNION_TERRITORY),
                ("Jammu and Kashmir", "JK", State.Type.UNION_TERRITORY),
                ("Ladakh", "LA", State.Type.UNION_TERRITORY),
                ("Lakshadweep", "LD", State.Type.UNION_TERRITORY),
                ("Puducherry", "PY", State.Type.UNION_TERRITORY),
            ]

            state_map = {}
            for name, code, stype in states_data:
                st, _ = State.objects.update_or_create(
                    country=country,
                    name=name,
                    defaults={"code": code, "type": stype}
                )
                state_map[name] = st

            # 3. Districts, Cities & Localities
            hierarchy_data = {
                "Odisha": {
                    "Khordha": {
                        "cities": {
                            "Bhubaneswar": {
                                "tier": 2,
                                "is_metro": False,
                                "areas": [
                                    ("Patia", "751024"),
                                    ("Chandrasekharpur", "751016"),
                                    ("Khandagiri", "751030"),
                                    ("Infocity", "751024"),
                                    ("Nayapalli (Jayadev Vihar)", "751012"),
                                    ("Saheed Nagar", "751007"),
                                    ("Mancheswar Industrial Estate", "751010"),
                                    ("Janpath / Master Canteen", "751001"),
                                ]
                            },
                            "Khordha Town": {
                                "tier": 3,
                                "is_metro": False,
                                "areas": [("Main Market", "752055"), ("Collectorate Road", "752055")]
                            }
                        }
                    },
                    "Deogarh": {
                        "cities": {
                            "Deogarh": {
                                "tier": 3,
                                "is_metro": False,
                                "areas": [
                                    ("Reamal", "768109"),
                                    ("Barkote", "768110"),
                                    ("Main Town", "768119"),
                                    ("Pradhanpat Waterfall Road", "768119"),
                                ]
                            }
                        }
                    },
                    "Cuttack": {
                        "cities": {
                            "Cuttack": {
                                "tier": 2,
                                "is_metro": False,
                                "areas": [
                                    ("Badambadi", "753012"),
                                    ("CDA Sector", "753014"),
                                    ("Link Road", "753012"),
                                    ("Chauliaganj", "753004"),
                                ]
                            }
                        }
                    },
                    "Puri": {
                        "cities": {
                            "Puri": {
                                "tier": 3,
                                "is_metro": False,
                                "areas": [
                                    ("Grand Road (Bada Danda)", "752001"),
                                    ("Sea Beach Road", "752002"),
                                    ("VIP Road", "752002"),
                                ]
                            }
                        }
                    },
                    "Sambalpur": {
                        "cities": {
                            "Sambalpur": {
                                "tier": 2,
                                "is_metro": False,
                                "areas": [
                                    ("Burla (VSSUT Hub)", "768018"),
                                    ("Ainthapali", "768004"),
                                    ("Dhanupali", "768005"),
                                ]
                            }
                        }
                    },
                    "Sundargarh": {
                        "cities": {
                            "Rourkela": {
                                "tier": 2,
                                "is_metro": False,
                                "areas": [
                                    ("Civil Township", "769004"),
                                    ("Panposh", "769004"),
                                    ("Koel Nagar", "769014"),
                                ]
                            }
                        }
                    }
                },
                "Maharashtra": {
                    "Mumbai": {
                        "cities": {
                            "Mumbai": {
                                "tier": 1,
                                "is_metro": True,
                                "areas": [
                                    ("Bandra Kurla Complex (BKC)", "400051"),
                                    ("Andheri East", "400069"),
                                    ("Powai Tech SEZ", "400076"),
                                    ("Lower Parel", "400013"),
                                    ("Nariman Point", "400021"),
                                ]
                            }
                        }
                    },
                    "Pune": {
                        "cities": {
                            "Pune": {
                                "tier": 1,
                                "is_metro": True,
                                "areas": [
                                    ("Hinjawadi IT Park", "411057"),
                                    ("Baner", "411045"),
                                    ("Wakad", "411057"),
                                    ("Viman Nagar", "411014"),
                                    ("Magarpatta Cybercity", "411028"),
                                ]
                            }
                        }
                    }
                },
                "Karnataka": {
                    "Bengaluru Urban": {
                        "cities": {
                            "Bengaluru": {
                                "tier": 1,
                                "is_metro": True,
                                "areas": [
                                    ("Electronic City", "560100"),
                                    ("Whitefield", "560066"),
                                    ("Koramangala", "560034"),
                                    ("Indiranagar", "560038"),
                                    ("HSR Layout", "560102"),
                                    ("Outer Ring Road (Bellandur)", "560103"),
                                ]
                            }
                        }
                    }
                },
                "Delhi": {
                    "New Delhi": {
                        "cities": {
                            "Delhi": {
                                "tier": 1,
                                "is_metro": True,
                                "areas": [
                                    ("Connaught Place", "110001"),
                                    ("Saket District Centre", "110017"),
                                    ("Nehru Place", "110019"),
                                    ("Dwarka", "110075"),
                                    ("Okhla Industrial Area", "110020"),
                                ]
                            }
                        }
                    }
                },
                "West Bengal": {
                    "Kolkata": {
                        "cities": {
                            "Kolkata": {
                                "tier": 1,
                                "is_metro": True,
                                "areas": [
                                    ("Salt Lake Sector V", "700091"),
                                    ("New Town Tech Park", "700156"),
                                    ("Park Street", "700016"),
                                    ("Rajarhat", "700135"),
                                ]
                            }
                        }
                    }
                },
                "Telangana": {
                    "Hyderabad": {
                        "cities": {
                            "Hyderabad": {
                                "tier": 1,
                                "is_metro": True,
                                "areas": [
                                    ("HITEC City", "500081"),
                                    ("Gachibowli", "500032"),
                                    ("Madhapur", "500081"),
                                    ("Kondapur", "500084"),
                                ]
                            }
                        }
                    }
                },
                "Tamil Nadu": {
                    "Chennai": {
                        "cities": {
                            "Chennai": {
                                "tier": 1,
                                "is_metro": True,
                                "areas": [
                                    ("Old Mahabalipuram Road (OMR)", "600096"),
                                    ("T. Nagar", "600017"),
                                    ("Guindy Cyber City", "600032"),
                                    ("Velachery", "600042"),
                                ]
                            }
                        }
                    }
                }
            }

            for state_name, districts in hierarchy_data.items():
                st = state_map.get(state_name)
                if not st:
                    continue
                for dist_name, ddata in districts.items():
                    dist, _ = District.objects.update_or_create(
                        state=st,
                        name=dist_name,
                        defaults={"headquarters": dist_name}
                    )
                    for city_name, cdata in ddata["cities"].items():
                        city, _ = City.objects.update_or_create(
                            state=st,
                            name=city_name,
                            defaults={
                                "district": dist,
                                "is_metro": cdata.get("is_metro", False),
                                "tier": cdata.get("tier", 2)
                            }
                        )
                        for area_name, pcode in cdata.get("areas", []):
                            area, _ = Area.objects.update_or_create(
                                city=city,
                                name=area_name
                            )
                            if pcode:
                                PinCode.objects.update_or_create(
                                    pin_code=pcode,
                                    state=st,
                                    defaults={
                                        "district": dist,
                                        "city": city,
                                        "area": area,
                                        "office_name": f"{area_name} PO"
                                    }
                                )

            self.stdout.write(self.style.SUCCESS("Location hierarchy seeded successfully."))

            # 4. Ensure verified test jobs exist with complete structured location data
            recruiter = User.objects.filter(role__in=[User.Role.RECRUITER, User.Role.COMPANY_ADMIN]).first()
            if not recruiter:
                recruiter = User.objects.filter(is_superuser=True).first()
            if not recruiter:
                recruiter = User.objects.create_user(
                    username="admin_recruiter",
                    email="admin@hirenexa.com",
                    role=User.Role.COMPANY_ADMIN
                )

            org = Organization.objects.first()
            if not org:
                org = Organization.objects.create(
                    name="HireNexa Technologies",
                    slug="hirenexa-tech",
                    industry="Software & AI",
                    city="Bhubaneswar",
                    state="Odisha",
                    district="Khordha",
                    area="Patia",
                    registered_office_address="Plot No. 12, Infocity SEZ, Patia, Bhubaneswar, Khordha, Odisha - 751024",
                    branch_office_address="Tech Park, Whitefield, Bengaluru, Karnataka - 560066",
                    is_active=True
                )

            sample_jobs = [
                {
                    "title": "Full Stack Developer (Python & React)",
                    "company_name": "HireNexa Innovations",
                    "department": "MCA / Engineering",
                    "target_course": Job.TargetCourse.MCA,
                    "vacancies": 8,
                    "job_type": Job.JobType.FULL_TIME,
                    "workplace_type": Job.WorkplaceType.HYBRID,
                    "country": "India",
                    "state": "Odisha",
                    "district": "Khordha",
                    "city": "Bhubaneswar",
                    "area": "Patia",
                    "pin_code": "751024",
                    "location": "Bhubaneswar, Odisha",
                    "salary_min": 700000,
                    "salary_max": 1200000,
                    "required_skills": "Python, Django, React, REST APIs, PostgreSQL, Git",
                    "description": "Develop scalable full stack web applications for recruitment analytics and CBT examinations."
                },
                {
                    "title": "Python & Django Backend Engineer",
                    "company_name": "CloudNine Infotech",
                    "department": "MCA / Computer Applications",
                    "target_course": Job.TargetCourse.MCA,
                    "vacancies": 5,
                    "job_type": Job.JobType.FULL_TIME,
                    "workplace_type": Job.WorkplaceType.ONSITE,
                    "country": "India",
                    "state": "Odisha",
                    "district": "Khordha",
                    "city": "Bhubaneswar",
                    "area": "Infocity",
                    "pin_code": "751024",
                    "location": "Bhubaneswar, Odisha",
                    "salary_min": 650000,
                    "salary_max": 1100000,
                    "required_skills": "Python, Django, PostgreSQL, Docker, Redis",
                    "description": "High-throughput backend systems engineering for enterprise cloud SaaS."
                },
                {
                    "title": "IoT & Embedded Systems Engineer",
                    "company_name": "GreenGrid Power Solutions",
                    "department": "Engineering / Electronics",
                    "target_course": Job.TargetCourse.BTECH,
                    "vacancies": 3,
                    "job_type": Job.JobType.FULL_TIME,
                    "workplace_type": Job.WorkplaceType.ONSITE,
                    "country": "India",
                    "state": "Odisha",
                    "district": "Deogarh",
                    "city": "Deogarh",
                    "area": "Reamal",
                    "pin_code": "768109",
                    "location": "Deogarh, Odisha",
                    "salary_min": 500000,
                    "salary_max": 850000,
                    "required_skills": "Embedded C, Microcontrollers, IoT Sensors, MQTT",
                    "description": "Develop and deploy solar microgrid remote monitoring hardware in Reamal and Deogarh district."
                },
                {
                    "title": "Cloud DevOps & Kubernetes Architect",
                    "company_name": "InfraScale Systems",
                    "department": "Cloud & Infrastructure",
                    "target_course": Job.TargetCourse.ALL,
                    "vacancies": 4,
                    "job_type": Job.JobType.FULL_TIME,
                    "workplace_type": Job.WorkplaceType.REMOTE,
                    "country": "India",
                    "state": "Karnataka",
                    "district": "Bengaluru Urban",
                    "city": "Bengaluru",
                    "area": "Electronic City",
                    "pin_code": "560100",
                    "location": "Remote - All India",
                    "salary_min": 1400000,
                    "salary_max": 2400000,
                    "required_skills": "Kubernetes, AWS, Terraform, Docker, CI/CD",
                    "description": "Architect mission-critical multi-region Kubernetes clusters with 99.99% uptime SLA."
                },
                {
                    "title": "AI/ML Research Engineer (LLM Specialization)",
                    "company_name": "NeuralNexa Labs",
                    "department": "MCA / Computer Science",
                    "target_course": Job.TargetCourse.MCA,
                    "vacancies": 4,
                    "job_type": Job.JobType.FULL_TIME,
                    "workplace_type": Job.WorkplaceType.ONSITE,
                    "country": "India",
                    "state": "Karnataka",
                    "district": "Bengaluru Urban",
                    "city": "Bengaluru",
                    "area": "Whitefield",
                    "pin_code": "560066",
                    "location": "Bengaluru, Karnataka",
                    "salary_min": 1600000,
                    "salary_max": 2800000,
                    "required_skills": "Python, PyTorch, LLMs, LangChain, Vector Databases",
                    "description": "Design and fine-tune domain-specific language models for career intelligence and resume parsing."
                },
                {
                    "title": "Backend Systems Engineer - Distributed Systems",
                    "company_name": "DataFlow Systems",
                    "department": "Engineering",
                    "target_course": Job.TargetCourse.BTECH,
                    "vacancies": 6,
                    "job_type": Job.JobType.FULL_TIME,
                    "workplace_type": Job.WorkplaceType.HYBRID,
                    "country": "India",
                    "state": "Maharashtra",
                    "district": "Pune",
                    "city": "Pune",
                    "area": "Hinjawadi IT Park",
                    "pin_code": "411057",
                    "location": "Pune, Maharashtra",
                    "salary_min": 1000000,
                    "salary_max": 1800000,
                    "required_skills": "Java, Spring Boot, Kafka, Microservices, SQL",
                    "description": "Build resilient low-latency distributed event messaging pipelines."
                },
                {
                    "title": "HR Manager & Talent Acquisition Lead",
                    "company_name": "Apex Enterprise Corp",
                    "department": "MBA / Human Resources",
                    "target_course": Job.TargetCourse.MBA,
                    "vacancies": 2,
                    "job_type": Job.JobType.FULL_TIME,
                    "workplace_type": Job.WorkplaceType.HYBRID,
                    "country": "India",
                    "state": "Maharashtra",
                    "district": "Mumbai",
                    "city": "Mumbai",
                    "area": "Bandra Kurla Complex (BKC)",
                    "pin_code": "400051",
                    "location": "Mumbai, Maharashtra",
                    "salary_min": 900000,
                    "salary_max": 1500000,
                    "required_skills": "HR Operations, Talent Acquisition, Employee Relations, Labor Laws",
                    "description": "Drive corporate executive campus recruitment and talent engagement programs."
                },
                {
                    "title": "Site Reliability Engineer (SRE)",
                    "company_name": "ReliabilityWorks",
                    "department": "Engineering / DevOps",
                    "target_course": Job.TargetCourse.ALL,
                    "vacancies": 3,
                    "job_type": Job.JobType.FULL_TIME,
                    "workplace_type": Job.WorkplaceType.REMOTE,
                    "country": "India",
                    "state": "",
                    "district": "",
                    "city": "",
                    "area": "",
                    "pin_code": "",
                    "location": "All India (Remote)",
                    "salary_min": 1200000,
                    "salary_max": 2000000,
                    "required_skills": "Linux, Python, Prometheus, Grafana, Incident Management",
                    "description": "Maintain reliability, observability and automated recovery across distributed microservices."
                },
                {
                    "title": "Strategic Marketing & Brand Specialist",
                    "company_name": "Zenith Marketing Group",
                    "department": "MBA / Marketing",
                    "target_course": Job.TargetCourse.MBA,
                    "vacancies": 3,
                    "job_type": Job.JobType.FULL_TIME,
                    "workplace_type": Job.WorkplaceType.ONSITE,
                    "country": "India",
                    "state": "Delhi",
                    "district": "New Delhi",
                    "city": "Delhi",
                    "area": "Connaught Place",
                    "pin_code": "110001",
                    "location": "Delhi NCR",
                    "salary_min": 850000,
                    "salary_max": 1400000,
                    "required_skills": "Digital Marketing, SEO/SEM, Brand Strategy, Marketing Analytics",
                    "description": "Lead pan-India B2B growth and digital demand generation initiatives."
                },
                {
                    "title": "QA Automation & Performance Testing Engineer",
                    "company_name": "QualityFirst Tech",
                    "department": "MCA / Computer Applications",
                    "target_course": Job.TargetCourse.MCA,
                    "vacancies": 4,
                    "job_type": Job.JobType.FULL_TIME,
                    "workplace_type": Job.WorkplaceType.HYBRID,
                    "country": "India",
                    "state": "West Bengal",
                    "district": "Kolkata",
                    "city": "Kolkata",
                    "area": "Salt Lake Sector V",
                    "pin_code": "700091",
                    "location": "Kolkata, West Bengal",
                    "salary_min": 600000,
                    "salary_max": 1000000,
                    "required_skills": "Selenium, PyTest, JMeter, Postman, CI/CD",
                    "description": "Automate comprehensive end-to-end regression and stress testing suites."
                },
                {
                    "title": "Mobile App Developer (Flutter & Kotlin)",
                    "company_name": "AppSphere Technologies",
                    "department": "Engineering / Mobile",
                    "target_course": Job.TargetCourse.ALL,
                    "vacancies": 3,
                    "job_type": Job.JobType.FULL_TIME,
                    "workplace_type": Job.WorkplaceType.HYBRID,
                    "country": "India",
                    "state": "Tamil Nadu",
                    "district": "Chennai",
                    "city": "Chennai",
                    "area": "Old Mahabalipuram Road (OMR)",
                    "pin_code": "600096",
                    "location": "Chennai, Tamil Nadu",
                    "salary_min": 750000,
                    "salary_max": 1300000,
                    "required_skills": "Flutter, Dart, Kotlin, Android SDK, REST APIs",
                    "description": "Build high-performance cross-platform iOS and Android career applications."
                },
                {
                    "title": "Frontend Engineer - React & Next.js",
                    "company_name": "WebScale Labs",
                    "department": "MCA / Computer Applications",
                    "target_course": Job.TargetCourse.MCA,
                    "vacancies": 5,
                    "job_type": Job.JobType.FULL_TIME,
                    "workplace_type": Job.WorkplaceType.HYBRID,
                    "country": "India",
                    "state": "Telangana",
                    "district": "Hyderabad",
                    "city": "Hyderabad",
                    "area": "HITEC City",
                    "pin_code": "500081",
                    "location": "Hyderabad, Telangana",
                    "salary_min": 800000,
                    "salary_max": 1400000,
                    "required_skills": "React, Next.js, TypeScript, Tailwind CSS, Redux Toolkit",
                    "description": "Create responsive, accessible, pixel-perfect user interfaces with real-time WebSocket state."
                }
            ]

            for jdata in sample_jobs:
                Job.objects.update_or_create(
                    title=jdata["title"],
                    company_name=jdata["company_name"],
                    defaults={
                        "organization": org,
                        "recruiter": recruiter,
                        "department": jdata["department"],
                        "target_course": jdata["target_course"],
                        "vacancies": jdata["vacancies"],
                        "job_type": jdata["job_type"],
                        "workplace_type": jdata["workplace_type"],
                        "country": jdata["country"],
                        "state": jdata["state"],
                        "district": jdata["district"],
                        "city": jdata["city"],
                        "area": jdata["area"],
                        "pin_code": jdata["pin_code"],
                        "location": jdata["location"],
                        "salary_min": jdata["salary_min"],
                        "salary_max": jdata["salary_max"],
                        "required_skills": jdata["required_skills"],
                        "description": jdata["description"],
                        "is_active": True
                    }
                )

            self.stdout.write(self.style.SUCCESS(f"Seeded {len(sample_jobs)} structured verified jobs successfully."))
