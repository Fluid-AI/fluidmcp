# Migration Guide: Existing Components to shadcn/ui + Tailwind

This guide helps you migrate your existing CSS-based components to use shadcn/ui components and Tailwind CSS utilities.

---

## 🎯 Migration Strategy

### Hybrid Approach (Recommended)
Keep existing CSS for now, use shadcn/ui for new features, and gradually migrate existing components.

**Benefits:**
- No breaking changes
- Immediate use of new UI system
- Gradual, low-risk migration
- Existing functionality remains stable

---

## 📋 Component Migration Priorities

### Phase 1: Low-Risk (Start Here) ✅
- New features and pages
- Static components (headers, footers)
- Simple buttons and badges
- Basic cards and containers

### Phase 2: Medium Priority
- Forms (leverage React Hook Form + Zod)
- Modals and dialogs
- Dropdowns and menus
- Navigation components

### Phase 3: High-Risk (Do Last)
- Complex stateful components
- Components with custom logic
- Critical business components
- Components with dependencies

---

## 🔄 Before & After Examples

### Example 1: Button Migration

#### Before (CSS-based)
```tsx
// Old component
import './Button.css'

function OldButton({ children, onClick, variant = 'primary' }) {
  return (
    <button className={`btn btn-${variant}`} onClick={onClick}>
      {children}
    </button>
  )
}
```

```css
/* Button.css */
.btn {
  padding: 0.5rem 1rem;
  border-radius: 0.375rem;
  font-weight: 500;
}

.btn-primary {
  background-color: #3b82f6;
  color: white;
}
```

#### After (shadcn/ui)
```tsx
import { Button } from "@/components/ui/button"

function NewButton({ children, onClick, variant = 'default' }) {
  return (
    <Button variant={variant} onClick={onClick}>
      {children}
    </Button>
  )
}

// Or use directly:
<Button variant="default">Click Me</Button>
<Button variant="secondary">Secondary</Button>
<Button variant="destructive">Delete</Button>
```

---

### Example 2: Card Migration

#### Before (CSS-based)
```tsx
// ServerCard.tsx
import './ServerCard.css'

function ServerCard({ server }) {
  return (
    <div className="server-card">
      <div className="server-card-header">
        <h3>{server.name}</h3>
        <span className={`status ${server.status}`}>
          {server.status}
        </span>
      </div>
      <div className="server-card-body">
        {server.description}
      </div>
    </div>
  )
}
```

#### After (shadcn/ui + Tailwind)
```tsx
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

function ServerCard({ server }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>{server.name}</CardTitle>
          <Badge variant={server.status === 'running' ? 'default' : 'secondary'}>
            {server.status}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-muted-foreground">{server.description}</p>
      </CardContent>
    </Card>
  )
}
```

---

### Example 3: Form Migration

#### Before (Custom Form)
```tsx
// OldForm.tsx
import './Form.css'

function OldForm({ onSubmit }) {
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!email.includes('@')) {
      setError('Invalid email')
      return
    }
    onSubmit({ email })
  }

  return (
    <form className="form" onSubmit={handleSubmit}>
      <div className="form-group">
        <label>Email</label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="form-input"
        />
        {error && <span className="error">{error}</span>}
      </div>
      <button type="submit" className="btn-primary">
        Submit
      </button>
    </form>
  )
}
```

#### After (shadcn/ui + React Hook Form + Zod)
```tsx
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import * as z from "zod"
import { Form, FormField, FormItem, FormLabel, FormControl, FormMessage } from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"

const formSchema = z.object({
  email: z.string().email("Invalid email address"),
})

function NewForm({ onSubmit }) {
  const form = useForm({
    resolver: zodResolver(formSchema),
    defaultValues: { email: "" },
  })

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Email</FormLabel>
              <FormControl>
                <Input type="email" placeholder="you@example.com" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit">Submit</Button>
      </form>
    </Form>
  )
}
```

---

## 🎨 CSS to Tailwind Class Mapping

### Common Patterns

| CSS Property | Tailwind Class |
|-------------|----------------|
| `display: flex` | `flex` |
| `flex-direction: column` | `flex-col` |
| `justify-content: space-between` | `justify-between` |
| `align-items: center` | `items-center` |
| `gap: 1rem` | `gap-4` |
| `padding: 1rem` | `p-4` |
| `margin-top: 2rem` | `mt-8` |
| `width: 100%` | `w-full` |
| `border-radius: 0.5rem` | `rounded-lg` |
| `font-weight: bold` | `font-bold` |
| `font-size: 1.5rem` | `text-2xl` |
| `color: #6b7280` | `text-gray-500` |

### Theme Colors

| Old CSS Variable | Tailwind Class |
|-----------------|----------------|
| `var(--color-text-secondary)` | `text-muted-foreground` |
| `var(--color-success)` | `text-green-600` or custom |
| `var(--color-warning)` | `text-yellow-600` or custom |
| `var(--color-error)` | `text-destructive` |
| `background: #1a1a1a` | `bg-background` |
| `color: #ffffff` | `text-foreground` |

---

## 📝 Step-by-Step Migration Process

### Step 1: Identify Component to Migrate
Choose a low-risk component (e.g., a simple card or button).

### Step 2: Find Equivalent shadcn/ui Component
Check [SHADCN_SETUP.md](./SHADCN_SETUP.md) for available components.

### Step 3: Create New Component File
```tsx
// components/NewServerCard.tsx
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"

export function NewServerCard({ server }) {
  return (
    <Card className="hover:shadow-lg transition-shadow">
      {/* Component content */}
    </Card>
  )
}
```

### Step 4: Test Side-by-Side
Temporarily render both versions to compare:
```tsx
<div className="grid grid-cols-2 gap-4">
  <OldServerCard server={server} />
  <NewServerCard server={server} />
</div>
```

### Step 5: Replace Old Component
Once satisfied, replace the old component with the new one.

### Step 6: Remove Old CSS
After migration, remove unused CSS files.

---

## 🛠️ Existing Components Analysis

### Your Current Components

#### ✅ Easy to Migrate (Priority 1)
- **LoadingSpinner** → Use `<Skeleton />` or custom with Tailwind
- **ErrorMessage** → Use `<Alert variant="destructive" />`
- **ServerCard** → Use `<Card />` components
- **Badges/Status** → Use `<Badge />` component

#### ⚠️ Medium Complexity (Priority 2)
- **ServerEnvForm** → Migrate to React Hook Form + shadcn Form components
- **Form components** (9 files) → Consider keeping if complex, or migrate gradually
- **Dialogs/Modals** → Use `<Dialog />` component

#### 🔴 Keep As-Is (For Now)
- **Dashboard layout** → Keep existing structure
- **Complex state management** → Don't migrate yet
- **ToolRunner** → Keep until stable

---

## 🚦 Migration Checklist

For each component you migrate:

- [ ] Component renders correctly
- [ ] All variants/states work
- [ ] Styles match (or improve) original
- [ ] Dark mode works correctly
- [ ] Responsive behavior maintained
- [ ] Accessibility preserved
- [ ] No console errors
- [ ] TypeScript types correct
- [ ] Tests pass (if applicable)
- [ ] Old CSS removed
- [ ] Documentation updated

---

## 💡 Pro Tips

### 1. Use `cn()` for Conditional Styling
```tsx
import { cn } from "@/lib/utils"

<Card className={cn(
  "base-styles",
  isActive && "border-primary",
  isDisabled && "opacity-50 pointer-events-none"
)} />
```

### 2. Extend Components with Custom Styles
```tsx
<Button className="bg-gradient-to-r from-purple-500 to-pink-500">
  Custom Gradient
</Button>
```

### 3. Create Wrapper Components
```tsx
// components/StatusBadge.tsx
import { Badge } from "@/components/ui/badge"

export function StatusBadge({ status }: { status: string }) {
  const variant = status === 'running' ? 'default' : 
                  status === 'stopped' ? 'secondary' : 
                  'destructive'
  
  return <Badge variant={variant}>{status}</Badge>
}
```

### 4. Leverage Tailwind @apply for Repeated Patterns
```css
/* If you need custom classes */
@layer components {
  .card-hover {
    @apply transition-all duration-200 hover:shadow-lg hover:-translate-y-1;
  }
}
```

---

## ⚡ Quick Wins

Start with these easy migrations for immediate benefits:

### 1. Replace All Buttons
```bash
# Find all button usages
grep -r "className.*btn" src/
```

Replace with:
```tsx
<Button variant="default">Click</Button>
```

### 2. Add Theme Toggle to Header
```tsx
import { ThemeToggle } from "@/components/theme-toggle"

// In your header component:
<ThemeToggle />
```

### 3. Use Tooltip for Better UX
```tsx
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"

<TooltipProvider>
  <Tooltip>
    <TooltipTrigger>Hover me</TooltipTrigger>
    <TooltipContent>
      <p>Helpful information</p>
    </TooltipContent>
  </Tooltip>
</TooltipProvider>
```

---

## 🎯 Success Metrics

Track your migration progress:

- **Components migrated**: ___ / ___ (22 existing components)
- **CSS lines removed**: ___ / 1,300+
- **Tailwind adoption**: ___%
- **Dark mode coverage**: ___%
- **Accessibility improvements**: Count

---

## 📞 Need Help?

If you encounter issues during migration:

1. Check [SHADCN_SETUP.md](./SHADCN_SETUP.md) for component examples
2. Visit the component showcase at `/showcase`
3. Review [shadcn/ui docs](https://ui.shadcn.com)
4. Check [Tailwind CSS docs](https://tailwindcss.com)

---

**Remember**: Migration is iterative. Start small, test thoroughly, and gradually improve your codebase.

🎉 Happy migrating!
