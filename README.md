# Self-Healing Agent 🤖

## ⚡ Setup & Configuration

### 1. GitHub Personal Access Token (PAT)

- Required for authenticating with GitHub MCP tools.
- Generate from [GitHub Developer Settings](https://github.com/settings/tokens?utm_source=chatgpt.com) → **Personal Access Tokens (classic)**.
- Minimum recommended scopes:
    - `repo:status`
    - `public_repo`
    - `read:user`
- Avoid `admin` or full repo permissions unless absolutely necessary.
- Store in `.env`:

```env
GITHUB_PERSONAL_ACCESS_TOKEN=<your_pat>

GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=<your_cloud_project_id>
GOOGLE_CLOUD_LOCATION=<your_cloud_location>
```

### 2. Vertex AI Integration (Optional)

For running on Vertex AI instead of local Gemini inference:

```shell
gcloud auth login 
gcloud config set project <PROJECT_ID> 
gcloud services enable aiplatform.googleapis.com
```

Add to `.env`:

```env
GOOGLE_GENAI_USE_VERTEXAI=TRUE GOOGLE_CLOUD_PROJECT=<PROJECT_ID> 
GOOGLE_CLOUD_LOCATION=us-central1
```

Source it:

```shell
set -o allexport && source .env && set +o allexport
```

### 3. MCP Toolbox (JIRA/Database Integration)

Download MCP Toolbox binary:

```shell
export OS="linux/amd64"  # linux/amd64, darwin/arm64, etc. 
curl -O --output-dir deployment/mcp-toolbox https://storage.googleapis.com/genai-toolbox/v0.6.0/$OS/toolbox 
chmod +x deployment/mcp-toolbox/toolbox
```

### 4. Cloud SQL (Postgres) for Ticket/Session Storage

Create Cloud SQL instance:

```shell
gcloud sql instances create software-assistant \
--database-version=POSTGRES_16 \
--tier=db-custom-1-3840 \
--region=us-central1 \
--edition=ENTERPRISE \
--root-password=admin
```

Create DB + table:

```shell
gcloud sql databases create tickets-db --instance=software-assistant
```

SQL schema (Cloud SQL Studio):

```sql
CREATE TABLE tickets (     
	ticket_id SERIAL PRIMARY KEY,     
	title VARCHAR(255) NOT NULL,     
	description TEXT,     
	assignee VARCHAR(100),     
	priority VARCHAR(50),     
	status VARCHAR(50) DEFAULT 'Open',     
	creation_time TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,     
	updated_time TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP 
);
```

Add vector embeddings (Vertex AI required):

```sql
ALTER TABLE tickets ADD COLUMN embedding vector(768) GENERATED ALWAYS AS    (embedding('text-embedding-005', description)) STORED;
```

### 5. Deploy MCP Toolbox to Cloud Run

Update `deployment/mcp-toolbox/tools.yaml` with your Cloud SQL connection, then:

```shell
gcloud run deploy toolbox \   
--image us-central1-docker.pkg.dev/database-toolbox/toolbox/toolbox:latest \   
--service-account toolbox-identity@$PROJECT_ID.iam.gserviceaccount.com \   
--region us-central1 \   
--set-secrets="/app/tools.yaml=tools:latest" \   
--set-env-vars="PROJECT_ID=$PROJECT_ID,DB_USER=postgres,DB_PASS=admin" \   
--args="--tools-file=/app/tools.yaml" \   
--args="--address=0.0.0.0" \   
--args="--port=8080" \   
--allow-unauthenticated
```

Store URL in `.env`:

```shell
MCP_TOOLBOX_URL=$(gcloud run services describe toolbox --region us-central1 --format "value(status.url)")
```

### 6. Deploy Self-Healing Agent to Cloud Run

Build + push image:

```shell
gcloud builds submit --region=us-central1 \   
--tag us-central1-docker.pkg.dev/$PROJECT_ID/adk-samples/self-healing-agent:latest
```

Deploy:

```shell
gcloud run deploy self-healing-agent \   
--image=us-central1-docker.pkg.dev/$PROJECT_ID/adk-samples/self-healing-agent:latest \   
--region=us-central1 \   
--allow-unauthenticated \   
--set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=us-central1,GOOGLE_GENAI_USE_VERTEXAI=TRUE,MCP_TOOLBOX_URL=$MCP_TOOLBOX_URL,GITHUB_PERSONAL_ACCESS_TOKEN=$GITHUB_PERSONAL_ACCESS_TOKEN"
```

Optional: Use **Cloud SQL for session storage**:

```shell
gcloud run deploy self-healing-agent-chat \   
--image=us-central1-docker.pkg.dev/$PROJECT_ID/adk-samples/self-healing-agent-chat:latest \   
--region=us-central1 \   
--allow-unauthenticated \   
--add-cloudsql-instances=$PROJECT_ID:us-central1:software-assistant \   
--set-env-vars="SESSION_SERVICE_URI=postgresql+pg8000://postgres:admin@/session-db?unix_sock=/cloudsql/$PROJECT_ID:us-central1:software-assistant/.s.PGSQL.5432&database=session-db" \   
--memory=1Gi 
--timeout=300 
--port=8080
```

## 🎥 Demo Workflow

Below is an example end-to-end flow of how the **Self-Healing Agent** operates in production - [Demo](https://drive.google.com/file/d/1k_X93PtFfk9QJh_9bpKX7QYCzjLF4ux9/view?usp=sharing):

1. **Error Detected**
    - An error occurs in a GKE application (e.g., service crash, stack trace in logs).
    - GKE log event is published to **Pub/Sub**.
        
2. **Trigger**
    - A **Cloud Function** consumes the Pub/Sub event.
    - Function invokes the **Root Agent**.
        
3. **Analysis Phase (Analysis Agent)**
    - Retrieves error logs, stack trace, and relevant code files (via GitHub MCP).
    - Performs root cause analysis.
    - Runs searches via **Google Search** and **StackOverflow API**.
    - Produces a **bug report** with:
        - Problem summary
        - Root cause hypothesis
        - Suggested fix
            
4. **Ticket Creation (JIRA Agent)**
    - Creates a JIRA issue with structured details from the bug report.
    - Adds severity/priority labels.
    - Links issue to corresponding repository/component.
        
5. **Code Remediation (Code Fixer Agent)**
    - Creates a new branch in GitHub.
    - Applies code changes following repo conventions.
    - Runs quality checks (SonarQube).
    - Pushes commit + opens a **Pull Request (PR)**.
        
6. **Project Management Sync (JIRA Agent)**
    - Updates the JIRA ticket with:
        - PR link
        - Status = “In Progress” → “In Review”
        - Additional comments (test coverage, fix details).
            
7. **Human Oversight (Optional)**
    - Maintainers can review and merge the PR.

        
