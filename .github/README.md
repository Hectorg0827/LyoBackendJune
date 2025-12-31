# GitHub Configuration

This directory contains GitHub-specific configuration files for the LyoBackendJune project.

## Pull Request Templates

### Default Template: `PULL_REQUEST_TEMPLATE.md`

The default template used for all pull requests. This is a general-purpose template suitable for:
- Bug fixes
- New features
- Documentation updates
- Refactoring
- Performance improvements
- Tests and CI/CD changes

**Usage:** Automatically applied when creating any new PR.

### Phase 2 Specific Template: `PULL_REQUEST_TEMPLATE_PHASE2.md`

A specialized template created specifically for the Phase 2: Predictive Intelligence deployment PR.

This template includes:
- Detailed Phase 2 implementation summary
- Comprehensive checklist for Phase 2 deployment
- Post-merge deployment instructions
- Phase 2 specific metrics and impact expectations

**Usage:** Reference this template when creating Phase 2-related PRs, or copy relevant sections into the default template.

## How to Use Templates

### Using the Default Template

When you create a new PR on GitHub, the default template will automatically populate the description field. Simply fill in the relevant sections.

### Using a Specific Template

If you want to use a specific template (e.g., Phase 2 template):

1. Create your PR normally
2. Delete the auto-populated content
3. Copy content from the desired template file
4. Fill in the relevant details

Or use query parameters:
```
https://github.com/Hectorg0827/LyoBackendJune/compare/main...your-branch?template=PULL_REQUEST_TEMPLATE_PHASE2.md
```

## Template Maintenance

- **Default template:** Keep this generic and applicable to all PRs
- **Specific templates:** Create new templates for major features or releases when needed
- **Naming:** Use descriptive names like `PULL_REQUEST_TEMPLATE_FEATURE_NAME.md`

## Future Templates

As the project grows, consider creating additional templates for:
- Security fixes
- Hotfixes
- Major version releases
- Breaking changes
- Database migrations

---

For more information about GitHub PR templates, see:
https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/creating-a-pull-request-template-for-your-repository
