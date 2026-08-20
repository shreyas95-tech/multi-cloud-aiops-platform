# Requirements Document

## Introduction

The Multi-Cloud AIOps Platform is a production-style prototype that enables users to manage cloud resources across AWS, Azure, and GCP through natural language queries. The platform uses an LLM-based agent exclusively for intent parsing and reasoning, while all execution is handled by a dedicated orchestrator and backend logic layer. The system provides cost monitoring, resource status tracking, and AI-based recommendations across all supported cloud providers.

## Glossary

- **Platform**: The Multi-Cloud AIOps Platform system as a whole
- **Frontend**: The minimal web UI that accepts user queries and displays results
- **Backend**: The FastAPI-based Python server handling API requests and business logic
- **AI_Layer**: The LLM-based agent responsible solely for intent parsing and reasoning from natural language queries
- **Orchestrator**: The custom Python logic layer that routes parsed intents to the appropriate cloud execution functions
- **Execution_Layer**: The set of cloud-specific functions that perform actual operations on AWS, Azure, and GCP
- **Monitoring_Layer**: The subsystem responsible for cost tracking, resource status, and AI-based recommendations
- **Intent_JSON**: The structured JSON representation of a parsed natural language query containing intent, cloud, action, and conditions fields
- **Cloud_Provider**: One of the supported cloud platforms (AWS, Azure, GCP)

## Requirements

### Requirement 1: Natural Language Query Input

**User Story:** As a platform user, I want to submit natural language queries describing cloud operations, so that I can manage multi-cloud resources without memorizing cloud-specific commands.

#### Acceptance Criteria

1. WHEN a user submits a natural language query via the Frontend, THE Backend SHALL accept the query within 2 seconds and forward it to the AI_Layer for parsing
2. THE Frontend SHALL provide a text input field for entering natural language queries with a maximum input length of 500 characters
3. WHEN a query is submitted, THE Frontend SHALL display a loading state until a response is received or until a timeout of 30 seconds has elapsed
4. WHEN a response is received from the Backend, THE Frontend SHALL display the result to the user in a structured format showing the parsed intent, target cloud provider, and operation summary
5. IF the Backend fails to process the query or the AI_Layer is unavailable, THEN THE Backend SHALL return an error response indicating the failure reason, and THE Frontend SHALL display an error message indicating the query could not be processed and preserve the user's original query text in the input field
6. IF the user submits an empty query or a query containing only whitespace, THEN THE Frontend SHALL prevent submission and display a validation message indicating that a non-empty query is required

### Requirement 2: Intent Parsing via AI Layer

**User Story:** As a platform operator, I want the AI Layer to parse natural language queries into structured intents, so that the system can route and execute actions deterministically.

#### Acceptance Criteria

1. WHEN a natural language query is received, THE AI_Layer SHALL parse it into an Intent_JSON object containing exactly four fields: intent (non-empty string), cloud (one of "AWS", "Azure", or "GCP"), action (non-empty string), and conditions (string, may be empty)
2. THE AI_Layer SHALL support parsing queries for starting, stopping, and managing cloud instances across AWS, Azure, and GCP
3. IF the AI_Layer cannot determine a valid intent from the query within 10 seconds, THEN THE AI_Layer SHALL return an error response containing a message indicating the reason parsing failed and the original query text
4. THE AI_Layer SHALL NOT execute any cloud operations directly
5. FOR ALL valid Intent_JSON objects, parsing then serializing then parsing SHALL produce an equivalent Intent_JSON object (round-trip property)
6. IF the natural language query references a cloud provider other than AWS, Azure, or GCP, THEN THE AI_Layer SHALL return an error response indicating an unsupported cloud provider
7. IF the natural language query exceeds 500 characters in length, THEN THE AI_Layer SHALL return an error response indicating the query exceeds the maximum allowed length
8. WHEN a natural language query is received, THE AI_Layer SHALL return the parsed Intent_JSON object within 5 seconds under normal operating conditions

### Requirement 3: Orchestrator Routing

**User Story:** As a system architect, I want all cloud actions routed through an orchestrator layer, so that execution is decoupled from LLM reasoning and the system remains extensible.

#### Acceptance Criteria

1. WHEN an Intent_JSON is received from the AI_Layer, THE Orchestrator SHALL validate that the Intent_JSON contains a non-empty cloud provider field and a non-empty action field, and route it to the appropriate Execution_Layer function within 500 milliseconds of receipt
2. THE Orchestrator SHALL maintain a provider registry that maps each combination of cloud provider and action to a specific execution function, supporting a minimum of 3 cloud providers with up to 20 actions each
3. IF the Intent_JSON contains a cloud provider not present in the provider registry, or an action not registered for the specified provider, THEN THE Orchestrator SHALL return an error response indicating the unsupported provider or action without invoking any Execution_Layer function
4. IF the Intent_JSON is missing required fields or contains malformed data, THEN THE Orchestrator SHALL return an error response indicating the validation failure and preserve the original intent for audit logging
5. THE Orchestrator SHALL NOT communicate directly with cloud provider APIs; all cloud interactions SHALL be delegated to the Execution_Layer
6. WHEN routing an action, THE Orchestrator SHALL log the intent identifier, target cloud provider, action name, and timestamp for audit purposes before invoking the Execution_Layer function
7. WHEN a new cloud provider or action is added to the provider registry, THE Orchestrator SHALL route intents for that provider and action without requiring modification to existing routing logic

### Requirement 4: AWS Execution Functions

**User Story:** As a user, I want to start and stop AWS instances through the platform, so that I can manage AWS resources via natural language.

#### Acceptance Criteria

1. WHEN a start action for AWS is routed by the Orchestrator, THE Execution_Layer SHALL call the AWS EC2 API via boto3 to start the instance identified by the provided instance ID (matching the pattern `i-` followed by up to 17 hexadecimal characters)
2. WHEN a stop action for AWS is routed by the Orchestrator, THE Execution_Layer SHALL call the AWS EC2 API via boto3 to stop the instance identified by the provided instance ID (matching the pattern `i-` followed by up to 17 hexadecimal characters)
3. IF an AWS API call fails, THEN THE Execution_Layer SHALL return a structured error response containing the AWS error code, error message, and the instance ID that was targeted, within 30 seconds of the initial request
4. WHEN an AWS operation completes successfully, THE Execution_Layer SHALL return a confirmation containing the instance ID and the new instance state (one of: pending, running, stopping, stopped) within 60 seconds of the initial request
5. IF the provided instance ID does not match a valid EC2 instance ID format, THEN THE Execution_Layer SHALL return a structured error indicating invalid instance ID without making an API call to AWS
6. IF the target instance is already in the requested state (e.g., start requested on a running instance), THEN THE Execution_Layer SHALL return a structured response indicating the instance is already in the desired state along with the current instance state
7. WHEN an AWS execution function is invoked, THE Execution_Layer SHALL accept the request through the common interface shared with Azure and GCP implementations and return a response conforming to that same common interface structure

### Requirement 5: Azure Execution Functions

**User Story:** As a user, I want to start and stop Azure VMs through the platform, so that I can manage Azure resources via natural language.

#### Acceptance Criteria

1. WHEN a start action for Azure is routed by the Orchestrator, THE Execution_Layer SHALL call the Azure Compute API via the Azure SDK to start the VM identified by the specified subscription ID, resource group, and VM name
2. WHEN a stop action for Azure is routed by the Orchestrator, THE Execution_Layer SHALL call the Azure Compute API via the Azure SDK to stop (deallocate) the VM identified by the specified subscription ID, resource group, and VM name
3. IF an Azure API call fails, THEN THE Execution_Layer SHALL return a structured error containing the Azure error code, error message, and the VM identifier that was targeted, within 5 seconds of receiving the failure response
4. WHEN an Azure operation completes successfully, THE Execution_Layer SHALL return a confirmation containing the VM name, resource group, and the new power state (Running or Deallocated) within 120 seconds of initiating the request
5. IF the specified VM does not exist or the provided subscription ID or resource group is invalid, THEN THE Execution_Layer SHALL return a structured error indicating the resource was not found, without retrying the operation
6. IF authentication to the Azure API fails due to expired or invalid credentials, THEN THE Execution_Layer SHALL return a structured error indicating an authentication failure, including the subscription ID that was targeted
7. THE Execution_Layer SHALL conform to the common execution interface shared with AWS and GCP implementations by accepting input parameters and returning output in the same structured format defined for all cloud providers

### Requirement 6: GCP Execution Functions

**User Story:** As a user, I want to start and stop GCP instances through the platform, so that I can manage GCP resources via natural language.

#### Acceptance Criteria

1. WHEN a start action for GCP is routed by the Orchestrator, THE Execution_Layer SHALL call the GCP Compute Engine API via the google-cloud SDK to start the instance identified by the specified project ID, zone, and instance name
2. WHEN a stop action for GCP is routed by the Orchestrator, THE Execution_Layer SHALL call the GCP Compute Engine API via the google-cloud SDK to stop the instance identified by the specified project ID, zone, and instance name
3. IF a GCP API call fails, THEN THE Execution_Layer SHALL return a structured error containing the GCP HTTP error code, error message, and the instance identifier that was targeted, within 30 seconds of the initial request
4. WHEN a GCP operation completes successfully, THE Execution_Layer SHALL return a confirmation containing the instance name, zone, and the new instance state (RUNNING or TERMINATED) within 120 seconds of initiating the request
5. IF the specified instance does not exist or the provided project ID or zone is invalid, THEN THE Execution_Layer SHALL return a structured error indicating the resource was not found, without retrying the operation
6. IF authentication to the GCP API fails due to missing or invalid service account credentials, THEN THE Execution_Layer SHALL return a structured error indicating an authentication failure, including the project ID that was targeted
7. THE Execution_Layer SHALL conform to the common execution interface shared with AWS and Azure implementations by accepting input parameters and returning output in the same structured format defined for all cloud providers

### Requirement 7: Cost Monitoring

**User Story:** As a finance-aware user, I want to view cloud costs across all providers, so that I can make informed decisions about resource usage and cloud selection.

#### Acceptance Criteria

1. WHEN a cost query is received, THE Monitoring_Layer SHALL retrieve cost data from AWS Cost Explorer, Azure Cost Management, and GCP Billing APIs within 30 seconds and return results including provider name, resource type, cost amount, and currency for each line item
2. WHEN cost data is retrieved from multiple providers, THE Monitoring_Layer SHALL present cost data in a unified format that normalizes currency to a single base currency (USD) and groups costs by provider and resource type, regardless of the source cloud provider
3. WHEN a user asks which cloud is cheapest for a specified resource type, THE Monitoring_Layer SHALL compare costs across providers for that resource type over the queried time period and return the provider with the lowest total cost; IF two or more providers have equal cost, THEN THE Monitoring_Layer SHALL return all tied providers
4. WHEN a cost query includes a time period, THE Monitoring_Layer SHALL return cost data filtered to that period, supporting ranges from 1 day up to 12 months in the past
5. IF a cost query does not specify a time period, THEN THE Monitoring_Layer SHALL default to the current calendar month (from the 1st to the current date)
6. IF one or more provider APIs are unavailable or return an error during a cost query, THEN THE Monitoring_Layer SHALL return available cost data from the remaining providers and indicate which providers failed with an error message identifying the unavailable provider
7. IF none of the provider APIs respond within 30 seconds, THEN THE Monitoring_Layer SHALL return an error indication stating that cost data is temporarily unavailable

### Requirement 8: Resource Status Monitoring

**User Story:** As an operations engineer, I want to see the status of cloud resources across all providers, so that I can monitor infrastructure health from a single interface.

#### Acceptance Criteria

1. WHEN a status query is received, THE Monitoring_Layer SHALL retrieve the current state of specified resources from the target Cloud_Provider and return results within 30 seconds
2. WHEN a status query is received, THE Monitoring_Layer SHALL report resource status including resource identifier, cloud provider name, instance state (running, stopped, or terminated), and CPU utilization as a percentage from 0 to 100 rounded to one decimal place
3. IF CPU utilization data is not available from the Cloud_Provider, THEN THE Monitoring_Layer SHALL return a null value for CPU utilization and include an indicator that the metric is unavailable
4. THE Monitoring_Layer SHALL present resource status in a unified format across all supported cloud providers, containing at minimum: resource identifier, provider name, instance state, and CPU utilization
5. IF the target Cloud_Provider API is unreachable or returns an error, THEN THE Monitoring_Layer SHALL return a partial response containing results from reachable providers and an error indication identifying the failed provider

### Requirement 9: AI-Based Recommendations

**User Story:** As a platform user, I want to receive AI-generated recommendations for cost optimization and resource management, so that I can improve efficiency across cloud providers.

#### Acceptance Criteria

1. WHEN monitoring data covering at least 24 hours of resource usage is available, THE AI_Layer SHALL generate a minimum of one and a maximum of 50 recommendations for cost optimization based on resource usage patterns, where each recommendation includes the recommended action, target resource identifier, affected cloud provider, and estimated cost saving expressed as a monetary value per month
2. THE AI_Layer SHALL provide each recommendation in natural language consisting of no more than 500 characters that specifies the recommended action, the target resource, and the expected benefit expressed as a quantified cost saving or performance improvement
3. WHEN a user requests recommendations, THE Platform SHALL return available recommendations within 30 seconds without automatically executing any suggested actions
4. IF the AI_Layer cannot generate recommendations due to insufficient monitoring data or service unavailability, THEN THE Platform SHALL return a response indicating the reason no recommendations are available and the minimum conditions required before recommendations can be generated
5. WHEN a user requests recommendations, THE Platform SHALL include a timestamp indicating when each recommendation was last generated, so the user can assess the recency of the advice

### Requirement 10: API Layer (FastAPI Backend)

**User Story:** As a developer integrating with the platform, I want a well-structured REST API, so that the frontend and external tools can interact with the platform reliably.

#### Acceptance Criteria

1. THE Backend SHALL expose a POST endpoint for submitting natural language queries that accepts a request body containing a query string of no more than 2000 characters and returns a JSON response within 10 seconds
2. THE Backend SHALL expose a GET endpoint for retrieving resource status across cloud providers that returns a JSON array of resource objects, with a maximum of 500 resources per response
3. THE Backend SHALL expose a GET endpoint for retrieving cost data across cloud providers that returns a JSON array of cost entries, with a maximum of 500 entries per response
4. THE Backend SHALL expose a GET endpoint for retrieving AI-based recommendations that returns a JSON array of recommendation objects, with a maximum of 100 recommendations per response
5. IF an API request fails validation, THEN THE Backend SHALL return a 422 response containing a JSON body with a field indicating which parameter failed and a human-readable description of the validation rule that was violated
6. THE Backend SHALL return all API responses in JSON format using a consistent envelope structure containing a status field, a data field for successful results, and an error field for failure details
7. IF an API request targets a valid endpoint but the downstream service (AI Layer, Orchestrator, or Monitoring Layer) is unreachable or returns an error, THEN THE Backend SHALL return a 502 response with a JSON body indicating which service failed and preserve any previously submitted query without data loss
8. THE Backend SHALL include CORS headers in all responses that permit requests from the web frontend origin
9. IF an API request is made to a non-existent endpoint, THEN THE Backend SHALL return a 404 response with a JSON body following the consistent envelope structure

### Requirement 11: System Extensibility

**User Story:** As a platform maintainer, I want the system to be cloud-agnostic and extensible, so that new cloud providers can be added without modifying existing orchestration logic.

#### Acceptance Criteria

1. THE Orchestrator SHALL use a provider registry pattern implemented as a dictionary mapping (cloud_provider, action) tuples to execution functions, allowing new Cloud_Provider implementations to be registered by adding entries without modifying existing routing logic
2. THE Execution_Layer SHALL define a common interface as a Python abstract base class with methods start_instance(params: dict) -> dict and stop_instance(params: dict) -> dict that all cloud provider implementations must inherit and implement
3. THE Monitoring_Layer SHALL use a unified data format defined as a Python dataclass containing fields for provider name, resource identifier, metric name, metric value, and timestamp that abstracts provider-specific response structures
4. WHEN a new cloud provider implementation is added by implementing the common interface and registering in the provider registry, THE Orchestrator SHALL route intents for that provider without requiring changes to any existing orchestration, monitoring, or execution code
5. THE Platform SHALL allow a new cloud provider to be added by creating no more than one new module file and modifying no more than one existing configuration or registry file
