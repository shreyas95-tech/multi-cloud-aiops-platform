# Implementation Plan: Multi-Cloud AIOps Platform

## Overview

This plan implements the Multi-Cloud AIOps Platform in Python using FastAPI. The implementation follows the provider registry pattern with an LLM-as-parser architecture. Tasks are ordered to establish foundational types first, then build each layer incrementally, wiring everything together at the end.

## Tasks

- [x] 1. Set up project structure and core data models
  - [x] 1.1 Create project directory structure and install dependencies
    - Create the directory layout: `backend/`, `backend/ai_layer/`, `backend/orchestrator/`, `backend/execution/`, `backend/monitoring/`, `backend/api/`, `backend/models/`, `frontend/`, `tests/unit/`, `tests/property/`, `tests/integration/`
    - Create `backend/requirements.txt` with dependencies: fastapi, uvicorn, boto3, azure-mgmt-compute, azure-identity, google-cloud-compute, httpx, hypothesis, pytest, pytest-asyncio, pydantic
    - Create `backend/__init__.py` and all subpackage `__init__.py` files
    - _Requirements: 10.1, 11.1, 11.2_

  - [x] 1.2 Implement core data models
    - Create `backend/models/intent.py` with the `IntentJSON` dataclass (fields: intent, cloud, action, conditions)
    - Create `backend/models/execution.py` with the `ExecutionResult` dataclass (fields: success, provider, resource_id, action, state, error_code, error_message, metadata)
    - Create `backend/models/monitoring.py` with `CostEntry`, `ResourceStatus`, `CostComparison`, and `TimePeriod` dataclasses
    - Create `backend/models/recommendation.py` with the `Recommendation` dataclass (fields: action, resource_id, provider, estimated_saving, generated_at)
    - Create `backend/models/api.py` with the `APIResponse` dataclass (fields: status, data, error)
    - _Requirements: 2.1, 7.2, 8.2, 9.1, 10.6, 11.3_

  - [x] 1.3 Write property tests for data models
    - **Property 2: Intent_JSON structural invariant** — generate random IntentJSON objects and verify all four fields are present with correct types
    - **Property 3: Intent_JSON round-trip** — serialize and deserialize IntentJSON, verify equivalence
    - **Validates: Requirements 2.1, 2.5**

- [x] 2. Implement AI Layer (Intent Parser)
  - [x] 2.1 Implement the AILayer service class
    - Create `backend/ai_layer/parser.py` with `AILayer` class
    - Implement `parse_intent(query: str) -> IntentJSON` method that calls an LLM API and returns structured Intent_JSON
    - Implement input validation: reject queries > 500 characters (raise `QueryTooLongError`), reject unsupported providers (raise `UnsupportedProviderError`)
    - Implement `generate_recommendations(monitoring_data) -> list[Recommendation]` method
    - Add 10-second timeout for parsing with appropriate error handling
    - Create custom exception classes in `backend/ai_layer/exceptions.py`: `ParseError`, `UnsupportedProviderError`, `QueryTooLongError`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6, 2.7, 2.8, 9.1, 9.2, 9.4_

  - [x] 2.2 Write property tests for AI Layer input validation
    - **Property 4: AI Layer input validation errors** — generate random queries referencing unsupported providers or exceeding 500 chars, verify error responses
    - **Validates: Requirements 2.6, 2.7**

  - [x] 2.3 Write unit tests for AI Layer
    - Test parsing of specific query examples for each provider (start/stop)
    - Test error cases: unparseable queries, unsupported providers, queries exceeding 500 chars
    - Test timeout behavior
    - _Requirements: 2.1, 2.3, 2.6, 2.7_

- [x] 3. Implement Orchestrator with Provider Registry
  - [x] 3.1 Implement the Orchestrator class with provider registry
    - Create `backend/orchestrator/orchestrator.py` with `Orchestrator` class
    - Implement `_registry: dict[tuple[str, str], Callable]` as the provider registry
    - Implement `register(provider, action, handler)` method for dynamic registration
    - Implement `route(intent: IntentJSON) -> ExecutionResult` method that validates the intent and looks up `(cloud, action)` in the registry
    - Add validation: reject empty cloud field, reject empty action field, reject unregistered (cloud, action) pairs
    - Implement audit logging: log intent_id, provider, action, timestamp before invocation
    - Raise `UnsupportedProviderError`, `UnsupportedActionError`, `ValidationError` on failures
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 11.1_

  - [x] 3.2 Write property tests for Orchestrator routing
    - **Property 5: Orchestrator routes valid intents correctly** — generate random valid (cloud, action) pairs registered in the registry, verify routing succeeds
    - **Property 6: Orchestrator rejects unregistered provider/action pairs** — generate random (cloud, action) pairs NOT in registry, verify error and no invocation
    - **Property 7: Orchestrator rejects malformed intents** — generate IntentJSON with empty cloud or action, verify validation error
    - **Property 8: Orchestrator audit logging** — route valid intents, verify audit log entries contain required fields before execution
    - **Property 9: Dynamic provider registration and routing** — dynamically register new pairs, verify routing succeeds without modifying existing logic
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.6, 3.7, 11.4**

  - [x] 3.3 Write unit tests for Orchestrator
    - Test routing for each registered (provider, action) pair
    - Test rejection for unregistered pairs
    - Test validation for malformed intents (missing fields)
    - Test audit log output format
    - _Requirements: 3.1, 3.3, 3.4, 3.6_

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement Execution Layer (Cloud Providers)
  - [x] 5.1 Implement CloudProvider abstract base class
    - Create `backend/execution/base.py` with `CloudProvider` ABC
    - Define abstract methods: `start_instance(params: dict) -> dict`, `stop_instance(params: dict) -> dict`
    - _Requirements: 11.2, 4.7, 5.7, 6.7_

  - [x] 5.2 Implement AWSProvider
    - Create `backend/execution/aws_provider.py` with `AWSProvider(CloudProvider)` class
    - Implement `start_instance` using boto3 EC2 client
    - Implement `stop_instance` using boto3 EC2 client
    - Add instance ID format validation (pattern `i-[0-9a-f]{1,17}`) — reject invalid IDs without making API calls
    - Handle already-in-state scenarios (return current state info)
    - Return `ExecutionResult` with provider-specific error codes on failure
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [x] 5.3 Implement AzureProvider
    - Create `backend/execution/azure_provider.py` with `AzureProvider(CloudProvider)` class
    - Implement `start_instance` using azure-mgmt-compute SDK (accepting subscription_id, resource_group, vm_name in params)
    - Implement `stop_instance` using azure-mgmt-compute SDK (deallocate)
    - Handle authentication failures with structured error (include subscription ID)
    - Handle resource-not-found scenarios
    - Return `ExecutionResult` conforming to common interface
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [x] 5.4 Implement GCPProvider
    - Create `backend/execution/gcp_provider.py` with `GCPProvider(CloudProvider)` class
    - Implement `start_instance` using google-cloud-compute SDK (accepting project_id, zone, instance_name in params)
    - Implement `stop_instance` using google-cloud-compute SDK
    - Handle authentication failures with structured error (include project ID)
    - Handle resource-not-found scenarios
    - Return `ExecutionResult` conforming to common interface
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [x] 5.5 Write property tests for Execution Layer
    - **Property 10: Execution error response structure (cross-provider)** — generate random cloud API failures, verify structured error contains error code, message, and resource_id
    - **Property 11: Execution success response structure (cross-provider)** — generate random successful operations, verify ExecutionResult contains resource_id and new state
    - **Property 12: AWS instance ID format validation** — generate random strings not matching `i-[0-9a-f]{1,17}`, verify rejection without API call
    - **Validates: Requirements 4.3, 4.4, 4.5, 4.7, 5.3, 5.4, 5.7, 6.3, 6.4, 6.7**

  - [x] 5.6 Write unit tests for Execution Layer
    - Test AWS start/stop with mocked boto3 for success and failure
    - Test Azure start/stop with mocked Azure SDK for success, failure, and auth errors
    - Test GCP start/stop with mocked google-cloud SDK for success, failure, and auth errors
    - Test already-in-state handling for all providers
    - _Requirements: 4.1, 4.2, 4.6, 5.1, 5.2, 5.5, 5.6, 6.1, 6.2, 6.5, 6.6_

- [x] 6. Implement Monitoring Layer
  - [x] 6.1 Implement cost monitoring
    - Create `backend/monitoring/monitoring.py` with `MonitoringLayer` class
    - Implement `get_costs(time_period: Optional[TimePeriod]) -> list[CostEntry]` — queries AWS Cost Explorer, Azure Cost Management, GCP Billing APIs
    - Normalize all currencies to USD
    - Default to current calendar month if no time period specified
    - Support time period filtering from 1 day to 12 months in the past
    - Handle partial provider failures: return available data + error indicators for failed providers
    - Implement `compare_costs(resource_type, time_period) -> CostComparison` — identify cheapest provider(s), handle ties
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [x] 6.2 Implement resource status monitoring
    - Implement `get_resource_status(provider: Optional[str]) -> list[ResourceStatus]` in `MonitoringLayer`
    - Retrieve instance state (running/stopped/terminated) and CPU utilization from each provider
    - Normalize CPU utilization to 0.0-100.0 rounded to 1 decimal place
    - Return null CPU with availability indicator if metric unavailable
    - Handle partial provider failures gracefully
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 6.3 Write property tests for Monitoring Layer
    - **Property 13: Cost data normalization** — generate random cost entries with various currencies, verify all normalized to USD in CostEntry format
    - **Property 14: Cheapest provider comparison** — generate random cost datasets, verify correct identification of cheapest provider(s) including ties
    - **Property 15: Cost time period filtering** — generate random time periods and cost entries, verify only entries within range are returned
    - **Property 16: Partial provider failure resilience** — simulate random subset of provider failures, verify remaining data returned with error indicators
    - **Property 17: Resource status unified structure** — generate random resource statuses, verify ResourceStatus structure with correct field types and value ranges
    - **Validates: Requirements 7.2, 7.3, 7.4, 7.6, 8.2, 8.3, 8.4, 8.5**

  - [x] 6.4 Write unit tests for Monitoring Layer
    - Test cost retrieval with mocked cloud APIs
    - Test default time period (current month)
    - Test cost comparison with tied providers
    - Test resource status normalization
    - Test partial failure handling
    - _Requirements: 7.1, 7.5, 7.6, 8.1, 8.5_

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement FastAPI Backend (API Layer)
  - [x] 8.1 Implement FastAPI application with CORS and envelope structure
    - Create `backend/api/main.py` with FastAPI app instance
    - Configure CORS middleware to permit requests from the web frontend origin
    - Implement `APIResponse` envelope wrapper utility that wraps all responses in `{status, data, error}` format
    - Configure 404 handler for non-existent endpoints using the envelope structure
    - _Requirements: 10.6, 10.8, 10.9_

  - [x] 8.2 Implement POST /api/query endpoint
    - Create `backend/api/routes/query.py`
    - Accept JSON body with `query` string (max 2000 chars)
    - Validate input: return 422 with field name and rule description on failure
    - Forward to AI Layer for parsing, then pass IntentJSON to Orchestrator
    - Return ExecutionResult wrapped in APIResponse envelope
    - Handle downstream failures: return 502 with service name identification
    - _Requirements: 1.1, 10.1, 10.5, 10.6, 10.7_

  - [x] 8.3 Implement GET /api/status endpoint
    - Create `backend/api/routes/status.py`
    - Call MonitoringLayer.get_resource_status()
    - Return JSON array of ResourceStatus objects (max 500 per response) wrapped in APIResponse envelope
    - Handle downstream failures with 502 response
    - _Requirements: 10.2, 10.6, 10.7_

  - [x] 8.4 Implement GET /api/costs endpoint
    - Create `backend/api/routes/costs.py`
    - Accept optional query params for time period
    - Call MonitoringLayer.get_costs()
    - Return JSON array of CostEntry objects (max 500 per response) wrapped in APIResponse envelope
    - Handle downstream failures with 502 response
    - _Requirements: 10.3, 10.6, 10.7_

  - [x] 8.5 Implement GET /api/recommendations endpoint
    - Create `backend/api/routes/recommendations.py`
    - Call AILayer.generate_recommendations() with monitoring data
    - Return JSON array of Recommendation objects (max 100 per response) wrapped in APIResponse envelope
    - Handle insufficient data and service unavailability errors
    - _Requirements: 9.3, 9.4, 9.5, 10.4, 10.6, 10.7_

  - [x] 8.6 Write property tests for API Layer
    - **Property 19: API envelope consistency** — generate random successful and error responses, verify envelope structure
    - **Property 20: API validation error responses** — generate random invalid requests, verify 422 with field name and rule description
    - **Property 21: Downstream failure error responses** — simulate random downstream failures, verify 502 with service identification
    - **Property 22: CORS headers present** — generate random requests, verify CORS headers in all responses
    - **Validates: Requirements 10.5, 10.6, 10.7, 10.8**

  - [x] 8.7 Write unit tests for API Layer
    - Test each endpoint with valid requests
    - Test 422 responses for invalid inputs
    - Test 502 responses for downstream failures
    - Test 404 for non-existent endpoints
    - Test CORS header presence
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.7, 10.8, 10.9_

- [x] 9. Implement Recommendations Layer
  - [x] 9.1 Implement recommendation generation logic
    - Wire `AILayer.generate_recommendations()` with `MonitoringLayer` data
    - Validate minimum 24 hours of monitoring data before generating recommendations
    - Enforce recommendation constraints: 1-50 results, max 500 chars per description
    - Include ISO 8601 timestamp on each recommendation
    - Handle insufficient data gracefully with informative error
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 9.2 Write property tests for Recommendations
    - **Property 18: Recommendation structure invariants** — generate random monitoring datasets, verify output constraints (1-50 count, ≤500 chars, valid ISO 8601 timestamp, monetary value, resource ID, provider)
    - **Validates: Requirements 9.1, 9.2, 9.5**

- [x] 10. Implement Frontend
  - [x] 10.1 Create minimal web UI
    - Create `frontend/index.html` with query input field (max 500 chars), submit button, loading indicator, and results display area
    - Create `frontend/app.js` with API client logic
    - Implement client-side validation: prevent submission of empty/whitespace-only queries with validation message
    - Implement loading state display on query submission (with 30-second timeout)
    - Implement structured result display showing parsed intent, target cloud provider, and operation summary
    - Implement error display that preserves user's original query text in the input field on failure
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 10.2 Write property test for frontend input validation
    - **Property 1: Whitespace query rejection** — generate random whitespace-only strings, verify submission is prevented
    - **Validates: Requirements 1.6**

- [x] 11. Integration and wiring
  - [x] 11.1 Wire all components together
    - Create `backend/api/dependencies.py` to instantiate and configure AILayer, Orchestrator, MonitoringLayer, and all CloudProviders
    - Register all (provider, action) pairs in the Orchestrator's provider registry: (AWS, start_instance), (AWS, stop_instance), (Azure, start_instance), (Azure, stop_instance), (GCP, start_instance), (GCP, stop_instance)
    - Wire FastAPI dependency injection to provide services to route handlers
    - Create `backend/main.py` as the application entry point that imports the FastAPI app and starts uvicorn
    - _Requirements: 3.2, 3.7, 11.1, 11.4, 11.5_

  - [x] 11.2 Write integration tests
    - Test full request flow: query → parse → route → execute → response (with mocked cloud SDKs)
    - Test monitoring flow: request → retrieve → normalize → respond
    - Test error propagation: AI Layer failure, Orchestrator validation failure, cloud API failure
    - Test CORS headers in end-to-end responses
    - Test partial failure scenarios in monitoring
    - _Requirements: 1.1, 3.1, 7.6, 8.5, 10.6, 10.7, 10.8_

- [x] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (22 total)
- Unit tests validate specific examples and edge cases
- All cloud SDK calls should be mocked in tests; no real cloud API calls during testing
- The AI Layer LLM integration can use a mock/stub during development and testing

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["1.3", "2.1", "3.1", "5.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "3.2", "3.3", "5.2", "5.3", "5.4"] },
    { "id": 4, "tasks": ["5.5", "5.6", "6.1"] },
    { "id": 5, "tasks": ["6.2"] },
    { "id": 6, "tasks": ["6.3", "6.4", "8.1"] },
    { "id": 7, "tasks": ["8.2", "8.3", "8.4", "8.5", "9.1", "10.1"] },
    { "id": 8, "tasks": ["8.6", "8.7", "9.2", "10.2", "11.1"] },
    { "id": 9, "tasks": ["11.2"] }
  ]
}
```
