# File Hub Frontend

React-based frontend for the File Hub application, built with TypeScript and modern web technologies.

## 🚀 Technology Stack

- React 18.x
- TypeScript 4.x
- React Router 6.x
- TanStack Query (React Query) for data fetching
- Axios for API communication
- Tailwind CSS for styling
- Heroicons for icons
- ESLint for code linting
- Prettier for code formatting
- Docker for containerization

## 📋 Prerequisites

- Node.js 18.x or higher
- npm 8.x or higher
- Docker (if using containerized setup)

## 🛠️ Installation & Setup

### Local Development

1. **Install Dependencies**
   ```bash
   npm install
   ```

2. **Start Development Server**
   ```bash
   npm start
   ```
   Access the application at http://localhost:3000

### Docker Setup

```bash
# Build the image
docker build -t file-hub-frontend .

# Run the container
docker run -p 3000:3000 file-hub-frontend
```

## 📁 Project Structure

```
src/
├── components/     # React components
├── hooks/         # Custom React hooks
├── services/      # API services
├── types/         # TypeScript types
└── utils/         # Utility functions
```

## 🔧 Available Scripts

### Development
- `npm start`: Start development server
- `npm run build`: Build for production
- `npm test`: Run tests
- `npm run eject`: Eject from Create React App

### Code Quality & Formatting
- `npm run lint`: Run ESLint to check for code issues
- `npm run lint:fix`: Run ESLint and automatically fix issues
- `npm run format`: Format code with Prettier
- `npm run format:check`: Check if code is formatted correctly
- `npm run typecheck`: Run TypeScript type checking

## 🌐 API Integration

The frontend communicates with the backend API at `http://localhost:8000/api`. Key endpoints:

- `GET /api/files/`: List all files
- `POST /api/files/`: Upload new file
- `GET /api/files/<id>/`: Get file details
- `DELETE /api/files/<id>/`: Delete file

## 🔒 Environment Variables

```env
REACT_APP_API_URL=http://localhost:8000/api
```

## 🧹 Code Quality & Standards

This project uses ESLint and Prettier to maintain consistent code quality and formatting.

### Linting with ESLint

ESLint is configured with rules for React, TypeScript, accessibility, and import organization.

```bash
# Check for linting issues
npm run lint

# Automatically fix linting issues
npm run lint:fix
```

**Configuration**: `.eslintrc.js`

### Code Formatting with Prettier

Prettier ensures consistent code formatting across the project.

```bash
# Format all files
npm run format

# Check if files are properly formatted
npm run format:check
```

**Configuration**: `.prettierrc`

### TypeScript Type Checking

```bash
# Run TypeScript compiler without emitting files (type checking only)
npm run typecheck
```

### Pre-commit Workflow

Before committing code, run:

```bash
# 1. Check types
npm run typecheck

# 2. Lint and fix issues
npm run lint:fix

# 3. Format code
npm run format

# 4. Run tests
npm test
```

### IDE Integration

For the best development experience, configure your IDE:

#### VS Code
Install these extensions:
- ESLint (`ms-vscode.vscode-eslint`)
- Prettier (`esbenp.prettier-vscode`)

Add to your VS Code settings:
```json
{
  "editor.formatOnSave": true,
  "editor.defaultFormatter": "esbenp.prettier-vscode",
  "editor.codeActionsOnSave": {
    "source.fixAll.eslint": true
  }
}
```

## 🐛 Troubleshooting

1. **Build Issues**
   - Clear npm cache: `npm cache clean --force`
   - Delete node_modules: `rm -rf node_modules && npm install`

2. **API Connection Issues**
   - Verify API URL in environment variables
   - Check CORS settings
   - Ensure backend is running

3. **Linting Issues**
   - Run `npm run lint:fix` to auto-fix most issues
   - Check `.eslintrc.js` for rule configurations
   - For TypeScript errors, run `npm run typecheck`

4. **Formatting Issues**
   - Run `npm run format` to format all files
   - Check `.prettierrc` for formatting rules
   - Ensure your IDE is configured to use Prettier
