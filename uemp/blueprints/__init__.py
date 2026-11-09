"""
blueprints package — one sub-package per area of the website.

    auth/        login, logout, change password
    main/        home page redirect
    student/     student self-service portal
    lecturer/    lecturer portal (courses, score entry)
    admin/       department-level administration (also used by Super Admin)
    superadmin/  university-wide administration

Each area has its own routes and forms, so a team can work on one area
without touching the others.
"""
