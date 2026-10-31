Feature: Edge-to-Cloud Resilient File Synchronization
  As an Edge Device Firmware System
  I want to securely package, encrypt, and synchronize sensor telemetry with the Cloud Gateway
  Even when the edge uplink experiences intermittent connectivity or network drops
  So that data integrity is guaranteed and no duplicate records are processed in the cloud.

  @bdd @resilience @e2e
  Scenario: Resilient upload recovers after transient network failures
    Given a Linux edge device with 3 spooled medical telemetry batches
    And the cloud gateway experiences intermittent 503 transient failures
    When the edge device initiates spool synchronization
    Then the resilient client retries with exponential backoff and jitter
    And all 3 telemetry batches are successfully acknowledged by the cloud gateway
    And the cloud gateway processes each batch effectively once with zero duplicates

