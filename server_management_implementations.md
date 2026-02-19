# MCP Server Management -- Implementation Plan

## Overview

This feature introduces a centralized **Server Management Page** that
enables users to:

-   Add MCP servers
-   Edit server configurations
-   Soft delete servers
-   Enable / disable servers
-   Search, filter, and paginate configurations

The implementation follows a **backend-first strategy**, ensuring
lifecycle safety before UI integration.

------------------------------------------------------------------------

# Architecture Overview

## High-Level System Flow

``` mermaid
flowchart LR
    A[Manage Page UI] --> B[FastAPI Management API]
    B --> C[DatabaseManager]
    C --> D[(MongoDB - fluidmcp_servers)]

    A --> E[Dashboard UI]
    E --> B
```

------------------------------------------------------------------------

## Runtime vs Configuration Separation

``` mermaid
flowchart TD
    Dashboard[Dashboard Layer<br>Runtime Control] -->|Start/Stop| Runtime
    Manage[Manage Page<br>Configuration CRUD] --> ConfigDB[(Configuration Store)]

    Runtime --> ConfigDB
```

  Layer         Responsibility
  ------------- --------------------------------------
  Dashboard     Runtime control (start/stop/monitor)
  Manage Page   Configuration lifecycle (CRUD)
  Backend       Enforce invariants and safety rules
  Database      Persistent configuration storage

------------------------------------------------------------------------

# Enabled Toggle Behavior (Final Decision)

## When `enabled = true`

-   Server appears on Dashboard
-   Can be started/stopped
-   Fully operational

## When `enabled = false`

-   Hidden from Dashboard
-   Visible in Manage page
-   Cannot be started (backend enforced)
-   Acts as a "pause without data loss"

## When `deleted_at` is set

-   Hidden everywhere
-   Soft-deleted (recoverable in future)

------------------------------------------------------------------------

# Lifecycle State Diagram

``` mermaid
stateDiagram-v2
    [*] --> Enabled
    Enabled --> Running
    Running --> Stopped
    Stopped --> Running

    Enabled --> Disabled
    Disabled --> Enabled

    Disabled --> SoftDeleted
    Stopped --> SoftDeleted
```

------------------------------------------------------------------------

# Lifecycle Invariants

-   Disabled ⇒ Not Running
-   Soft Deleted ⇒ Not Running
-   Cannot edit while running
-   Delete auto-stops before soft delete
-   ID immutable after creation

------------------------------------------------------------------------

# Implementation Phases

## Phase 1 -- Backend Soft Delete Foundation

Scope: - Add `deleted_at` field to model - Implement
`soft_delete_server_config` - Update list queries to exclude
soft-deleted records - Convert DELETE endpoint to soft delete - Block
starting disabled servers - Ensure runtime cache cleanup

Goal: Introduce safe lifecycle control before UI changes.

------------------------------------------------------------------------

## Phase 2 -- Frontend Infrastructure Cleanup

Scope: - Extract reusable Navbar component - Remove navigation
duplication - Extend API service with CRUD methods - Update type
definitions (`deleted_at` field)

Goal: Clean architectural foundation before new UI work.

------------------------------------------------------------------------

## Phase 3 -- Server Management UI

Scope: - Create `useServerManagement` hook - Create reusable
`ServerForm` - Build `/servers/manage` page - Implement: - Search -
Filter (all/running/stopped/error) - Pagination (10 per page) -
Create/Edit modal - Delete confirmation - Enabled toggle

Goal: Deliver full CRUD UI layer.

------------------------------------------------------------------------

## Phase 4 -- Integration & Validation

Scope: - Add route to `App.tsx` - Ensure Dashboard respects enabled
filtering - Confirm backend validation blocks invalid actions - Verify
cross-page behavior sync

Goal: End-to-end functional correctness.

------------------------------------------------------------------------

# PR Strategy

## PR 1 -- Backend + Infrastructure Cleanup

Includes: - Phase 1 (Backend Soft Delete) - Phase 2 (Frontend
Infrastructure Cleanup)

Why combine?

-   Both are structural changes
-   No visible feature yet
-   Reduces review complexity
-   Backend invariants secured before UI

Risk Level: Medium\
Impact: Internal architecture only

------------------------------------------------------------------------

## PR 2 -- Management UI + Integration

Includes: - Phase 3 (UI) - Phase 4 (Integration) - Full testing
verification

Why separate?

-   Large visible feature
-   Easier for reviewers to test independently
-   Clear feature-focused PR
-   Minimizes mixed backend/frontend logic in one review

Risk Level: Medium-High\
Impact: Visible feature addition

------------------------------------------------------------------------

# Risk Analysis

## 1️⃣ Soft Delete Migration Risk

Risk: - Accidentally exposing soft-deleted servers - Inconsistent
filtering logic

Mitigation: - Always exclude `deleted_at` in list queries - Add backend
tests for filtering behavior

------------------------------------------------------------------------

## 2️⃣ Navbar Extraction Risk

Risk: - UI regression across 5 pages - Broken active link highlighting

Mitigation: - Manual cross-page testing - Confirm active route detection
works

------------------------------------------------------------------------

## 3️⃣ Runtime / Enabled Desync

Risk: - Disabled server still appears running - Running server disabled
without stopping

Mitigation: - Backend blocks start when disabled - Delete auto-stops

------------------------------------------------------------------------

## 4️⃣ Edit While Running

Risk: - UI allows edit but backend rejects

Mitigation: - Disable Edit button if running - Keep backend validation
as safety net

------------------------------------------------------------------------

## 5️⃣ Cache Inconsistency

Risk: - In-memory configs not removed on soft delete

Mitigation: - Explicit cache removal in DELETE handler - Integration
testing after deletion

------------------------------------------------------------------------

# Testing Plan

## Backend Tests

-   Soft delete sets `deleted_at`
-   Disabled server cannot start (403)
-   Editing running server blocked
-   List excludes soft-deleted servers
-   Auto-stop before delete works

------------------------------------------------------------------------

## Frontend Manual Testing

Create: - Valid ID → Success - Invalid ID → Blocked - Duplicate ID →
Error surfaced

Edit: - Stopped server → Success - Running server → Button disabled

Delete: - Running → Warning + auto-stop - Stopped → Soft delete

Enabled Toggle: - Disable → Hidden from Dashboard - Enable → Reappears

Search & Filter: - Name - ID - Status - Pagination (10+ entries)

Navbar: - Works across all pages - Active highlighting correct

------------------------------------------------------------------------

# Estimated Complexity

Backend: Medium\
Frontend Infrastructure: Medium\
Management UI: Medium-High\
Integration: Medium

Overall: Controlled complexity via staged rollout
