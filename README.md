# Nuboxed

<p align="center">
  Europe-focused multi-retailer ecommerce marketplace platform built with Django and Django REST Framework.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/Django-4.2-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django 4.2" />
  <img src="https://img.shields.io/badge/MySQL-Database-4479A1?style=for-the-badge&logo=mysql&logoColor=white" alt="MySQL" />
  <img src="https://img.shields.io/badge/Redis-Queue-DC382D?style=for-the-badge&logo=redis&logoColor=white" alt="Redis" />
  <img src="https://img.shields.io/badge/Docker-Containerized-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />
</p>

## About

Nuboxed is a scalable and secure Python-based marketplace application designed for modern web operations. The platform is being built in phases, starting with core infrastructure and backend foundations, then expanding into marketplace modules and retailer workflows.

## Technology Stack

<table align="center">
  <tr>
    <td align="center" width="140">
      <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/python/python-original.svg" width="52" alt="Python" /><br />
      <strong>Python</strong><br />
      <sub>Backend Language</sub>
    </td>
    <td align="center" width="140">
      <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/django/django-plain.svg" width="52" alt="Django" /><br />
      <strong>Django</strong><br />
      <sub>Web Framework</sub>
    </td>
    <td align="center" width="140">
      <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/mysql/mysql-original.svg" width="52" alt="MySQL" /><br />
      <strong>MySQL</strong><br />
      <sub>Relational Database</sub>
    </td>
    <td align="center" width="140">
      <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/redis/redis-original.svg" width="52" alt="Redis" /><br />
      <strong>Redis</strong><br />
      <sub>Queue & Cache</sub>
    </td>
    <td align="center" width="140">
      <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/docker/docker-original.svg" width="52" alt="Docker" /><br />
      <strong>Docker</strong><br />
      <sub>Container Platform</sub>
    </td>
  </tr>
</table>

## Core Stack

- Python 3.12
- Django 4.2 LTS
- Django REST Framework
- MySQL
- Redis and Celery
- Docker
- S3-compatible object storage

## Repository Structure

- `docs/architecture/` system planning and phased roadmap
- `backend/` Django project, apps, and API base
- `deploy/` deployment-specific documentation
- `requirements.txt` top-level install passthrough

## Backend Quick Start

See [backend/README.md](/usr/local/var/www/Nuboxed/backend/README.md:1) for setup, JWT endpoints, Celery, and environment settings.

## Current Scope

This repository currently contains:

- architecture and delivery planning
- Django backend base project
- phased app and module structure
- environment configuration templates

## Next Step

Phase 1 focuses on environment setup, authentication, RBAC, catalog primitives, tenant boundaries, and API standards.
