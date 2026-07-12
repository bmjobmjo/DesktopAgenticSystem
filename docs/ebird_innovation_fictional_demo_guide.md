# Ebird Innovation Fictional Demo Guide

## Overview

Ebird Innovation is a fictional office environment packaged inside OASIS as a fixed demonstration database. It is designed to help evaluators explore how OASIS handles office automation, HR workflows, project operations, expenses, purchase approvals, and day-to-day execution tracking without needing real company data.

This demo office includes a complete working dataset for:

- users and employees
- departments and reporting hierarchy
- projects and project teams
- holidays and leave requests
- expenses and purchase requests
- project tasks, daily tasks, and work diary
- project notes, memory summaries, and document records

The dataset is intentionally fixed and repeatable. It does not generate random records or shift dates automatically.

## Fictional Company Profile

### Company Name

Ebird Innovation

### Team Structure

The fictional office includes these named staff members:

- Bijumon, CTO
- Arshadev, R&D Head
- Nissar, Sales and Marketing Head
- Roshna, Software Lead
- Sumesh, Lead Customer Support
- Jalan, Production Manager
- SreeDhanya, Software Engineer
- Visakh, Android Developer
- Dipin, Office Admin

### Business Lines

- eGate Automatic Gate Opening System
- eGard Home Security and Automation

### Active Projects

- eOffice - ERP
- eGate Development
- Android Smart Home

## How To Log In

Use the web UI or desktop/web runtime login page for the deployed OASIS instance.

### Demo URL

- `http://69.164.244.153:9090`

### Demo Login

Log in with the published demo account:

- username: `bijumon`
- password: `Ebird2020`

This login is intended for exploring the fictional Ebird Innovation demo office and its seeded workflows.

## What You Can Explore

### HR and Organization

- view all employees
- inspect reporting hierarchy
- review department assignments
- check employee skills and contact details
- browse leave balances and leave history

### Project Operations

- list active projects
- inspect project members
- read project notes and weekly updates
- review project memory summaries
- browse project-linked files and records

### Daily Work Tracking

- view seeded project tasks
- inspect task status and priorities
- review daily task entries
- read employee diary notes

### Finance and Approvals

- review expenses by project or category
- inspect purchase requests
- see approval actions and status changes

## Suggested Demo Flow

### 1. Start With Overview Queries

Use prompts like:

- `List all employees in Ebird Innovation`
- `Show all active projects`
- `List all purchase requests`
- `Show expenses by project`

### 2. Move Into HR Workflows

Try:

- `Who reports to Bijumon?`
- `Show leave history for Visakh`
- `List all holidays in 2026`
- `Show pending leave approvals`

### 3. Explore Project Delivery

Try:

- `Show project members for eOffice - ERP`
- `List open tasks`
- `Show work diary entries for Jalan`
- `What is the latest status of Android Smart Home?`

### 4. Explore Finance and Control

Try:

- `List expenses for eGate Development`
- `Show approved purchase requests`
- `Which purchase requests were rejected?`
- `Show purchase approval history`

## Safe Example Queries

These are useful for demonstrations:

- `List all employees in Ebird Innovation`
- `Show current leave balance for all employees`
- `List approved leave requests in June 2026`
- `Show all holidays in 2026`
- `List all active projects`
- `Show project members for Android Smart Home`
- `List open tasks`
- `Show daily tasks for Visakh`
- `Show work diary entries for SreeDhanya`
- `List expenses by category`
- `Show all purchase requests`
- `List project files for eOffice - ERP`

## Safe Example Modifications

These are good for showing controlled business updates:

- `Add a holiday on 2026-08-15 called Independence Day`
- `Create a casual leave request for Dipin on 2026-07-15`
- `Add an expense of INR 12500 for eOffice - ERP under Software and SaaS`
- `Create a new task for Visakh to fix notification retry issue`
- `Add a work diary entry for Roshna on 2026-07-04`
- `Approve Jalan's pending purchase request`

## Demo Data Scope

The seeded fictional office currently covers the date range:

- from `2026-01-01`
- through `2026-07-04`

This makes it suitable for historical demo queries, workflow exploration, and admin testing.

## What This Demo Is For

This fictional office is useful for:

- product demos
- workflow validation
- UI exploration
- admin training
- internal reviews
- testing prompt and agent behavior against realistic office data

## What This Demo Is Not

This dataset is not:

- real company data
- a rolling live operational feed
- a random data generator
- a production customer environment

## Publishing Note

This guide is written as a publishable content page for the OASIS Easy website. It can be published as:

- a product demo walkthrough
- a fictional office showcase page
- a getting-started guide for evaluators
- a support reference for hosted demo instances
