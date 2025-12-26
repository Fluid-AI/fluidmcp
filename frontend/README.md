# FluidMCP Frontend

A React + TypeScript frontend for interacting with MCP (Model Context Protocol) tools through the FluidMCP gateway. This UI provides a user-friendly interface for accessing various MCP tools, currently featuring an Airbnb search tool.

## Overview

This frontend application consumes MCP endpoints exposed by the FluidMCP gateway without modifying backend logic. It provides a clean, intuitive interface for users to interact with MCP tools through their browser.

## Tech Stack

- **React** (v19.2.0) - UI framework
- **TypeScript** (v5.9.3) - Type-safe JavaScript
- **Vite** (v7.2.4) - Fast build tool and dev server
- **React Router DOM** (v7.11.0) - Client-side routing
- **ESLint** - Code linting and quality

## Project Structure

```
frontend/
├── src/
│   ├── pages/                  # Page components
│   │   ├── Home.tsx           # Landing page with tool selection
│   │   └── Airbnb.tsx         # Airbnb search tool interface
│   ├── components/            # Reusable components
│   │   └── ListingCard.tsx    # Airbnb listing display component
│   ├── services/              # API and external services
│   │   └── api.ts             # FluidMCP backend API client
│   ├── assets/                # Static assets (images, etc.)
│   ├── App.tsx                # Main application with routing
│   ├── App.css                # Global styles
│   └── main.tsx               # Application entry point
├── public/                    # Public static files
├── vite.config.ts             # Vite configuration
├── tsconfig.json              # TypeScript configuration
├── package.json               # Dependencies and scripts
└── README.md                  # This file
```

## Getting Started

### Prerequisites

- Node.js (v18 or higher recommended)
- npm or yarn
- FluidMCP backend running (see root repository documentation)

### Installation

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Create environment configuration:
```bash
# Create .env file
touch .env
```

4. Configure the backend URL in `.env`:
```env
# For local development
VITE_API_BASE_URL=http://localhost:8090

# For GitHub Codespaces (replace with your Codespace URL)
# VITE_API_BASE_URL=https://<your-codespace-name>-8090.app.github.dev
```

### Running the Development Server

```bash
npm run dev
```

The application will be available at:
- Local: `http://localhost:5173`
- Codespaces: `https://<your-codespace-name>-5173.app.github.dev`

## Available Scripts

### Development
```bash
npm run dev        # Start development server with hot reload
```

### Production Build
```bash
npm run build      # Compile TypeScript and build for production
npm run preview    # Preview production build locally
```

### Code Quality
```bash
npm run lint       # Run ESLint to check code quality
```

## Environment Variables

The frontend uses Vite's environment variable system. Create a `.env` file in the frontend directory:

| Variable | Description | Example |
|----------|-------------|---------|
| `VITE_API_BASE_URL` | FluidMCP backend base URL | `http://localhost:8090` |

**Note:** All Vite environment variables must be prefixed with `VITE_` to be exposed to the client-side code.

## Architecture

### Routing

The application uses React Router for client-side routing:

- `/` - Home page displaying available MCP tools
- `/airbnb` - Airbnb search tool interface

### API Integration

The frontend communicates with the FluidMCP backend through the `services/api.ts` module:

- Sends JSON-RPC 2.0 formatted requests to MCP tools
- Handles pagination with cursor-based navigation
- Manages loading states and error handling
- Configurable backend URL via environment variables

### Component Architecture

- **Pages**: Top-level route components (`Home.tsx`, `Airbnb.tsx`)
- **Components**: Reusable UI components (`ListingCard.tsx`)
- **Services**: External API communication and data fetching

## Development Workflow

1. **Start the Backend**: Ensure FluidMCP backend is running on port 8090
2. **Start Frontend**: Run `npm run dev` to start the development server
3. **Make Changes**: Edit files in `src/` - changes will hot-reload
4. **Lint Code**: Run `npm run lint` to check code quality
5. **Build**: Run `npm run build` before committing to ensure no build errors

## Adding New MCP Tools

To add a new MCP tool to the frontend:

1. Create a new page component in `src/pages/`
2. Add the route in `src/App.tsx`
3. Create API service methods in `src/services/api.ts`
4. Add a link to the tool on the Home page
5. Implement the UI with appropriate state management

## Troubleshooting

### Backend Connection Issues

If you see connection errors:
1. Verify the FluidMCP backend is running
2. Check `VITE_API_BASE_URL` in your `.env` file
3. Ensure CORS is properly configured in the backend
4. For Codespaces, verify port forwarding is set to "Public"

### Build Errors

If TypeScript build fails:
1. Run `npm install` to ensure all dependencies are installed
2. Delete `node_modules` and reinstall if needed
3. Check for TypeScript errors with `npm run build`

### Hot Reload Not Working

1. Ensure you're using a modern browser
2. Try clearing browser cache
3. Restart the dev server

## Browser Support

- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)

## Contributing

When contributing to the frontend:
1. Follow the existing code structure and naming conventions
2. Use TypeScript for all new components
3. Run `npm run lint` before committing
4. Test in multiple browsers if making UI changes
5. Update this README if adding new features

## Related Documentation

- Root README: Complete system architecture and setup
- Backend Documentation: FluidMCP backend API reference
- MCP Protocol: Model Context Protocol specification

## License

See the root repository for license information.
