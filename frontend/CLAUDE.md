# CLAUDE.md - Frontend

This file provides guidance to Claude Code when working with the FluidMCP frontend codebase.

## Project Overview

The FluidMCP frontend is a React + TypeScript single-page application (SPA) that provides a user interface for interacting with MCP (Model Context Protocol) tools through the FluidMCP backend gateway. It uses Vite as the build tool for fast development and optimized production builds.

## Technology Stack

- **React 19.2.0**: Modern UI framework with hooks-based components
- **TypeScript 5.9.3**: Type-safe development
- **Vite 7.2.4**: Fast build tool and dev server
- **React Router DOM 7.11.0**: Client-side routing
- **ESLint**: Code quality and consistency

## Architecture

### Application Entry Point

**File**: `src/main.tsx`
- Initializes React application
- Wraps `<App />` with `<BrowserRouter>` for routing
- Mounts to `#root` element in `index.html`

### Routing Structure

**File**: `src/App.tsx`
- Central routing configuration
- Uses React Router's `<Routes>` and `<Route>` components
- Current routes:
  - `/` → `Home.tsx` (Landing page with tool selection)
  - `/airbnb` → `Airbnb.tsx` (Airbnb search interface)

### Component Organization

```
src/
├── pages/              # Route-level components (one per URL path)
│   ├── Home.tsx       # Landing page
│   └── Airbnb.tsx     # Airbnb search tool page
├── components/        # Reusable UI components
│   └── ListingCard.tsx
└── services/          # External integrations
    └── api.ts         # Backend API client
```

## Key Files and Components

### Pages

#### `src/pages/Home.tsx`
- **Purpose**: Landing page displaying available MCP tools
- **Current State**: Tools are hardcoded as static cards
- **Future**: Could be made dynamic by fetching available tools from backend
- **Styling**: Inline styles for simplicity
- **Navigation**: Uses `<Link>` from react-router-dom

#### `src/pages/Airbnb.tsx`
- **Purpose**: Full-featured Airbnb search interface
- **State Management**:
  - Form inputs: `location`, `checkin`, `checkout`, `adults`, `children`, `pets`
  - Search results: `listings` array
  - Pagination: `nextCursor`, `prevCursor`, `currentCursor`
  - UI state: `loading`, `error`, `sortBy`, `minPrice`, `maxPrice`
- **Key Functions**:
  - `handleSearch()`: Initiates new search with form parameters
  - `handleNextPage()`: Loads next page using cursor
  - `handlePreviousPage()`: Loads previous page using cursor history
  - Inline filtering and sorting logic for client-side operations
- **API Integration**: Calls `callAirbnbSearch()` from `services/api.ts`
- **Data Flow**:
  1. User fills form → `handleSearch()` called
  2. API request sent with parameters
  3. Response stored in state
  4. `ListingCard` components rendered for each result

### Components

#### `src/components/ListingCard.tsx`
- **Purpose**: Reusable card component for displaying individual Airbnb listings
- **Props**: `listing` object with:
  - `name`, `url`, `rating`, `reviewCount`
  - `price`, `type`, `persons`
  - `bedrooms`, `beds`, `baths`
  - `location`, `coordinates`
- **Features**:
  - Responsive card layout
  - External link to actual Airbnb listing
  - Displays all key listing information
  - Inline styling for consistency

### Services

#### `src/services/api.ts`
- **Purpose**: Centralized API communication with FluidMCP backend
- **Configuration**:
  - `BASE_URL` loaded from `import.meta.env.VITE_API_BASE_URL`
  - Must be set in `.env` file for proper operation
- **Functions**:
  - `callAirbnbSearch(payload)`: POST to `/airbnb/mcp/tools/call`
    - Accepts search parameters and optional cursor
    - Returns JSON-RPC formatted MCP tool response
    - Throws error if response not ok
- **Protocol**: Communicates using JSON-RPC 2.0 format expected by MCP tools

## State Management

### Current Approach
- **Local Component State**: Uses React's `useState` hooks
- **No Global State**: Each page manages its own state independently
- **Prop Drilling**: Minimal due to shallow component tree

### State Patterns in Airbnb.tsx
```typescript
// Form state
const [location, setLocation] = useState("");
const [checkin, setCheckin] = useState("");
// ... more form fields

// Results state
const [listings, setListings] = useState([]);
const [loading, setLoading] = useState(false);
const [error, setError] = useState("");

// Pagination state
const [nextCursor, setNextCursor] = useState(null);
const [prevCursor, setPrevCursor] = useState([]);
```

## Environment Variables

### Configuration
- **System**: Vite environment variables (must prefix with `VITE_`)
- **Access**: `import.meta.env.VITE_VARIABLE_NAME`
- **File**: `.env` in frontend root (not committed to git)

### Required Variables
```env
VITE_API_BASE_URL=http://localhost:8090
```

### Notes
- Variables are replaced at build time by Vite
- Only variables prefixed with `VITE_` are exposed to client code
- For Codespaces, use full Codespaces URL: `https://...-8090.app.github.dev`

## API Communication

### Request Format (JSON-RPC 2.0)
```typescript
{
  jsonrpc: "2.0",
  method: "tools/call",
  params: {
    name: "airbnb_search",
    arguments: {
      location: "Paris",
      checkin: "2025-03-01",
      checkout: "2025-03-05",
      adults: 2,
      cursor: "optional-pagination-cursor"
    }
  },
  id: 1
}
```

### Response Format
```typescript
{
  jsonrpc: "2.0",
  result: {
    content: [
      {
        type: "text",
        text: "{\"listings\": [...], \"nextCursor\": \"...\"}"
      }
    ]
  },
  id: 1
}
```

### Pagination
- **Cursor-based**: Backend returns `nextCursor` for next page
- **History**: Frontend stores cursor history in array for back navigation
- **Implementation**: See `Airbnb.tsx:handleNextPage()` and `handlePreviousPage()`

## Styling Approach

### Current Method
- **Inline Styles**: All styling done with React `style` prop
- **No CSS-in-JS Library**: Keeps bundle size small
- **Global Styles**: Minimal global styles in `App.css`
- **Consistency**: Color scheme and spacing defined inline

### Design Tokens (Inline)
```typescript
// Colors
background: "#0f172a"  // Dark slate
border: "#334155"      // Lighter slate
text: default (white/light)

// Spacing
padding: "1.25rem"
margin: "1.5rem"
borderRadius: 12
```

## Development Guidelines

### Adding a New MCP Tool Page

1. **Create Page Component**:
   ```typescript
   // src/pages/NewTool.tsx
   import { useState } from 'react';

   function NewTool() {
     const [results, setResults] = useState([]);
     // Add state management

     return (
       <div>
         {/* Add UI */}
       </div>
     );
   }

   export default NewTool;
   ```

2. **Add API Function**:
   ```typescript
   // src/services/api.ts
   export async function callNewTool(payload: any) {
     const response = await fetch(
       `${BASE_URL}/newtool/mcp/tools/call`,
       {
         method: "POST",
         headers: { "Content-Type": "application/json" },
         body: JSON.stringify(payload),
       }
     );
     if (!response.ok) throw new Error("Failed to fetch results");
     return response.json();
   }
   ```

3. **Add Route**:
   ```typescript
   // src/App.tsx
   import NewTool from "./pages/NewTool";

   // In Routes:
   <Route path="/newtool" element={<NewTool />} />
   ```

4. **Add to Home Page**:
   ```typescript
   // src/pages/Home.tsx
   <Link to="/newtool">New Tool</Link>
   ```

### Component Creation Guidelines

- **Use Functional Components**: No class components
- **TypeScript**: Always type props and state
- **Hooks**: Use React hooks for state and effects
- **Naming**: PascalCase for components, camelCase for functions
- **File Structure**: One component per file, named after component
- **Exports**: Use default export for main component

### Code Style

- **Formatting**: Follow existing indentation and spacing
- **Comments**: Add comments for complex logic or MCP-specific behavior
- **Error Handling**: Use try-catch and display user-friendly errors
- **Loading States**: Always show loading indicator during async operations
- **Type Safety**: Avoid `any` types where possible, prefer interfaces

## Common Patterns

### API Call with Error Handling
```typescript
const [loading, setLoading] = useState(false);
const [error, setError] = useState("");

async function fetchData() {
  setLoading(true);
  setError("");
  try {
    const result = await callAirbnbSearch(payload);
    // Process result
  } catch (err) {
    setError(err.message || "Something went wrong");
  } finally {
    setLoading(false);
  }
}
```

### Form Input Handling
```typescript
const [input, setInput] = useState("");

<input
  type="text"
  value={input}
  onChange={(e) => setInput(e.target.value)}
/>
```

### Conditional Rendering
```typescript
{loading && <p>Loading...</p>}
{error && <p style={{ color: "red" }}>{error}</p>}
{results.length > 0 && results.map(item => <Card key={item.id} {...item} />)}
```

## Build Configuration

### Vite Config (`vite.config.ts`)
- **Minimal Configuration**: Uses defaults
- **Plugins**: Only `@vitejs/plugin-react` for JSX transformation
- **Development**: Hot module replacement (HMR) enabled by default
- **Production**: Automatic code splitting and minification

### TypeScript Config (`tsconfig.json`)
- **Target**: ES2020
- **Module**: ESNext
- **Strict Mode**: Enabled for type safety
- **JSX**: react-jsx (new JSX transform)

## Testing Strategy

### Current State
- No automated tests currently implemented

### Future Recommendations
- **Unit Tests**: Vitest for component testing
- **E2E Tests**: Playwright or Cypress for full user flows
- **API Mocking**: MSW (Mock Service Worker) for API testing

## Performance Considerations

### Current Optimizations
- **Vite**: Fast dev server with native ESM
- **Code Splitting**: Automatic via Vite in production
- **React 19**: Automatic optimizations

### Future Improvements
- Add React.memo for expensive components
- Implement virtual scrolling for large listing arrays
- Add service worker for offline capability
- Implement lazy loading for routes

## Debugging

### Common Issues

1. **Environment Variables Not Loading**
   - Ensure variables are prefixed with `VITE_`
   - Restart dev server after changing `.env`
   - Check `import.meta.env` in browser console

2. **API Connection Failed**
   - Verify backend is running
   - Check `VITE_API_BASE_URL` is correct
   - Look for CORS errors in browser console
   - Ensure port forwarding is "Public" in Codespaces

3. **TypeScript Errors**
   - Run `npm run build` to see all type errors
   - Check imported types are correct
   - Ensure dependencies are installed

### Browser DevTools
- **React DevTools**: Install extension to inspect component state
- **Network Tab**: Monitor API requests and responses
- **Console**: Check for runtime errors and warnings

## Future Enhancements

### Planned Features
- Dynamic tool loading from backend
- User authentication and sessions
- Persistent state with localStorage
- More MCP tool integrations
- Shared component library
- Form validation library
- Toast notifications for feedback

### Technical Debt
- Replace inline styles with CSS modules or styled-components
- Add proper TypeScript interfaces for all API responses
- Implement proper error boundary components
- Add loading skeletons instead of generic loading text
- Create reusable form components

## Port Configuration

- **Frontend Dev Server**: `5173` (Vite default)
- **Backend API**: `8090` (FluidMCP gateway for single tool)
- **Backend API (All Tools)**: `8099` (FluidMCP unified gateway)

## Related Files

- `/CLAUDE.md`: Root project documentation
- `/frontend/README.md`: User-facing frontend documentation
- `/frontend/package.json`: Dependencies and scripts
- `/frontend/vite.config.ts`: Build configuration
