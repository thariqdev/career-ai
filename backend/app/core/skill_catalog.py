"""A fixed starter catalogue of common tech skills, used ONLY to suggest skills to add.

Nothing here is ever saved automatically: a match becomes a suggestion ("your CV also
mentions React"), and the user decides whether to add it (PROJECT_RULES.md: the
database is the source of truth, nothing is invented). The catalogue is plain data
written by hand, reviewed like any other code; it isn't generated at runtime.

Format: one skill per line, "Name | Category | alias, alias". Names in EXACT_CASE are
also everyday English words, so they only match when written exactly ("Go", "Swift"),
never "go" or "swift response". Deliberately left out because they match too much
ordinary text: single-letter languages ("R" in "R&D", "C" in "Grade C"), "Less" and
"Spring" ("Spring semester"); users can still add those skills themselves.
"""

from dataclasses import dataclass

_CATALOG = """
Python | Languages | Python3, Python 3
JavaScript | Languages | JS, ECMAScript, ES6
TypeScript | Languages | TS
Java | Languages |
C++ | Languages | CPP
C# | Languages | CSharp, C Sharp
Go | Languages | Golang
Rust | Languages |
Ruby | Languages |
PHP | Languages |
Swift | Languages |
Kotlin | Languages |
Scala | Languages |
MATLAB | Languages |
Perl | Languages |
Dart | Languages |
Elixir | Languages |
Erlang | Languages |
Haskell | Languages |
Clojure | Languages |
Lua | Languages |
Julia | Languages |
Objective-C | Languages | ObjC
Visual Basic | Languages | VB.NET
Groovy | Languages |
F# | Languages | FSharp
Bash | Languages | Shell scripting, Shell script
PowerShell | Languages |
SQL | Languages |
PL/SQL | Languages |
T-SQL | Languages |
HTML | Web | HTML5
CSS | Web | CSS3
Sass | Web | SCSS
Tailwind CSS | Web | Tailwind, TailwindCSS
Bootstrap | Web |
React | Frontend | React.js, ReactJS
Next.js | Frontend | NextJS
Vue.js | Frontend | Vue, VueJS
Nuxt.js | Frontend | Nuxt
Angular | Frontend | AngularJS
Svelte | Frontend | SvelteKit
Redux | Frontend |
jQuery | Frontend |
Webpack | Frontend |
Vite | Frontend |
Babel | Frontend |
React Native | Mobile |
Flutter | Mobile |
Android | Mobile | Android SDK
iOS | Mobile |
SwiftUI | Mobile |
Xamarin | Mobile |
Ionic | Mobile |
Node.js | Backend | NodeJS, Node
Express | Backend | Express.js, ExpressJS
NestJS | Backend | Nest.js
Django | Backend |
Flask | Backend |
FastAPI | Backend |
Spring Boot | Backend | SpringBoot, Spring Framework
Hibernate | Backend |
Ruby on Rails | Backend | Rails, RoR
Laravel | Backend |
Symfony | Backend |
ASP.NET | Backend | ASP.NET Core
.NET | Backend | dotnet, .NET Core
Entity Framework | Backend |
GraphQL | Backend |
REST APIs | Backend | REST, RESTful, REST API, RESTful APIs
gRPC | Backend |
WebSockets | Backend | WebSocket
Microservices | Backend | Microservice architecture
Celery | Backend |
SQLAlchemy | Backend |
Pydantic | Backend |
PostgreSQL | Databases | Postgres, PSQL
MySQL | Databases |
MariaDB | Databases |
SQLite | Databases |
Oracle Database | Databases | Oracle DB
Microsoft SQL Server | Databases | SQL Server, MSSQL
MongoDB | Databases | Mongo
Redis | Databases |
Cassandra | Databases | Apache Cassandra
DynamoDB | Databases |
Elasticsearch | Databases | Elastic Search
Neo4j | Databases |
Firebase | Databases | Firestore
Supabase | Databases |
Snowflake | Data |
BigQuery | Data |
Amazon Redshift | Data | Redshift
Apache Kafka | Data | Kafka
RabbitMQ | Data |
Apache Spark | Data | Spark, PySpark
Hadoop | Data | Apache Hadoop
Apache Airflow | Data | Airflow
dbt | Data |
Pandas | Data |
NumPy | Data |
SciPy | Data |
Matplotlib | Data |
Seaborn | Data |
Plotly | Data |
Jupyter | Data | Jupyter Notebook
ETL | Data |
Data Warehousing | Data | Data warehouse
Tableau | Data |
Power BI | Data | PowerBI
Looker | Data |
Excel | Data | Microsoft Excel, MS Excel
Machine Learning | AI | ML
Deep Learning | AI |
TensorFlow | AI |
PyTorch | AI |
Keras | AI |
scikit-learn | AI | sklearn, scikit learn
XGBoost | AI |
Natural Language Processing | AI | NLP
Computer Vision | AI | OpenCV
Large Language Models | AI | LLM, LLMs
Hugging Face | AI | HuggingFace, Transformers
LangChain | AI |
Retrieval-Augmented Generation | AI | RAG
Prompt Engineering | AI |
MLOps | AI |
Statistics | AI | Statistical analysis
AWS | Cloud | Amazon Web Services
Amazon EC2 | Cloud | EC2
Amazon S3 | Cloud | S3
AWS Lambda | Cloud | Lambda
Microsoft Azure | Cloud | Azure
Google Cloud | Cloud | GCP, Google Cloud Platform
Heroku | Cloud |
Vercel | Cloud |
Netlify | Cloud |
DigitalOcean | Cloud |
Serverless | Cloud |
Docker | DevOps | Docker Compose
Kubernetes | DevOps | K8s
Helm | DevOps |
Terraform | DevOps |
Ansible | DevOps |
Chef | DevOps |
Puppet | DevOps |
Jenkins | DevOps |
GitHub Actions | DevOps |
GitLab CI | DevOps | GitLab CI/CD
CircleCI | DevOps |
Travis CI | DevOps |
CI/CD | DevOps | CI CD, Continuous Integration, Continuous Delivery, Continuous Deployment
Nginx | DevOps |
Apache HTTP Server | DevOps | Apache httpd
Linux | DevOps | Ubuntu, Debian, CentOS, Red Hat
Unix | DevOps |
Prometheus | DevOps |
Grafana | DevOps |
Datadog | DevOps |
New Relic | DevOps |
Splunk | DevOps |
ELK Stack | DevOps | ELK, Kibana, Logstash
Infrastructure as Code | DevOps | IaC
Site Reliability Engineering | DevOps | SRE
Git | Tools |
GitHub | Tools |
GitLab | Tools |
Bitbucket | Tools |
Jira | Tools |
Confluence | Tools |
Postman | Tools |
Swagger | Tools | OpenAPI
VS Code | Tools | Visual Studio Code
Visual Studio | Tools |
IntelliJ IDEA | Tools | IntelliJ
Figma | Tools |
Maven | Tools |
Gradle | Tools |
npm | Tools |
Yarn | Tools |
pip | Tools |
Poetry | Tools |
Alembic | Tools |
Pytest | Testing |
JUnit | Testing |
Jest | Testing |
Mocha | Testing |
Cypress | Testing |
Playwright | Testing |
Selenium | Testing |
Unit Testing | Testing | Unit tests
Integration Testing | Testing | Integration tests
Test-Driven Development | Testing | TDD
OAuth | Security | OAuth2, OAuth 2.0
JWT | Security | JSON Web Tokens
OWASP | Security |
Cybersecurity | Security | Cyber security
Penetration Testing | Security | Pentesting
Encryption | Security |
Agile | Practices | Agile methodology
Scrum | Practices |
Kanban | Practices |
Object-Oriented Programming | Practices | OOP
Functional Programming | Practices |
Design Patterns | Practices |
Data Structures | Practices | Data structures and algorithms, DSA
Algorithms | Practices |
System Design | Practices |
Distributed Systems | Practices |
Event-Driven Architecture | Practices | Event driven architecture
Domain-Driven Design | Practices | DDD
Clean Architecture | Practices |
Code Review | Practices | Code reviews
API Design | Practices |
Database Design | Practices | Data modeling, Data modelling
Performance Optimization | Practices | Performance tuning
Accessibility | Practices | WCAG, a11y
Responsive Design | Practices |
UI/UX Design | Practices | UX, UI design, UX design
Technical Writing | Practices | Documentation
Communication | Soft skills |
Leadership | Soft skills |
Teamwork | Soft skills | Team player
Problem Solving | Soft skills | Problem-solving
Mentoring | Soft skills |
Project Management | Soft skills |
Stakeholder Management | Soft skills |
"""

# Also everyday words: matched only exactly as written, never case-insensitively.
EXACT_CASE = frozenset(
    {"Go", "Rust", "Swift", "Ruby", "Dart", "Julia", "Express", "Flask", "Helm",
     "Chef", "Puppet", "Jest", "Mocha", "Spark", "Node", "Lambda", "Communication",
     "Leadership", "Teamwork", "Mentoring", "Accessibility", "Encryption", "Statistics",
     "Algorithms", "Excel", "Looker", "Poetry", "Celery", "Pandas", "Ionic", "Unix",
     "Android", "Agile", "Kanban", "Serverless", "Microservices", "Vite", "Babel"}
)


@dataclass(frozen=True)
class CatalogSkill:
    name: str
    category: str
    aliases: tuple[str, ...]

    @property
    def terms(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)


def _parse(text: str) -> tuple[CatalogSkill, ...]:
    skills = []
    for line in text.strip().splitlines():
        name, category, aliases = (part.strip() for part in line.split("|"))
        skills.append(
            CatalogSkill(
                name=name,
                category=category,
                aliases=tuple(a.strip() for a in aliases.split(",") if a.strip()),
            )
        )
    return tuple(skills)


CATALOG: tuple[CatalogSkill, ...] = _parse(_CATALOG)
