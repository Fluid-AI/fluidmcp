# shadcn/ui Theme Setup - Complete Documentation

## ✅ Installation Complete

Your Vite + React + TypeScript project now has the complete shadcn/ui design system with:

- **44+ shadcn/ui components** fully configured
- **Tailwind CSS 3.4** with custom theme variables
- **Dark/Light mode support** (defaulting to dark)
- **Animation libraries**: Framer Motion, AOS, custom keyframes
- **Inter font** loaded from Google Fonts
- **Path aliases** configured (`@/` imports)
- **Complete type safety** with TypeScript

---

## 📁 Project Structure

```
src/
├── components/
│   ├── ui/               # 48 shadcn/ui components
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── dialog.tsx
│   │   ├── form.tsx
│   │   ├── input.tsx
│   │   ├── infinite-moving-cards.tsx  # Custom component
│   │   └── ... (44+ more)
│   ├── theme-provider.tsx    # Theme context wrapper
│   ├── theme-toggle.tsx      # Dark/light mode switcher
│   └── aos-init.tsx          # Animation library initializer
├── hooks/
│   ├── use-toast.ts          # Toast notification hook
│   ├── use-mobile.tsx        # Mobile breakpoint detection
│   └── ... (existing hooks)
├── lib/
│   └── utils.ts              # cn() utility function
├── pages/
│   ├── ComponentShowcase.tsx # Demo page with all components
│   ├── Dashboard.tsx
│   └── ... (existing pages)
├── styles/
│   └── globals.css           # Tailwind + theme variables
└── main.tsx                  # Entry point with providers
```

---

## 🚀 Quick Start

### Access Component Showcase
Visit **`/showcase`** route to see all components in action:
```
http://localhost:5173/ui/showcase
```

### Using Components

```tsx
import { Button } from "@/components/ui/button"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"

function MyComponent() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Welcome</CardTitle>
      </CardHeader>
      <CardContent>
        <Button>Click Me</Button>
      </CardContent>
    </Card>
  )
}
```

### Theme Toggle

```tsx
import { ThemeToggle } from "@/components/theme-toggle"

function Header() {
  return (
    <header>
      <h1>My App</h1>
      <ThemeToggle />
    </header>
  )
}
```

---

## 🎨 Available Components (44+)

### Layout & Structure
- `Accordion` - Collapsible content sections
- `Card` - Content container with header/footer
- `Separator` - Visual divider
- `Tabs` - Tab navigation interface
- `Sidebar` - Navigation sidebar with collapse

### Forms & Inputs
- `Button` - Interactive button with variants
- `Input` - Text input field
- `Textarea` - Multi-line text input
- `Checkbox` - Toggle checkbox
- `Radio Group` - Radio button selection
- `Switch` - Toggle switch
- `Slider` - Range slider
- `Select` - Dropdown selection
- `Form` - Form wrapper with validation
- `Label` - Form field label
- `Input OTP` - One-time password input
- `Calendar` - Date picker calendar
- `Date Picker` - Date selection input

### Feedback & Overlay
- `Alert` - Notification banner
- `Alert Dialog` - Modal confirmation dialog
- `Dialog` - Modal dialog
- `Drawer` - Slide-out panel
- `Toast` - Temporary notification
- `Toaster` - Toast container
- `Sonner` - Toast system (alternative)
- `Progress` - Progress indicator
- `Skeleton` - Loading placeholder

### Navigation & Menus
- `Dropdown Menu` - Action menu dropdown
- `Context Menu` - Right-click menu
- `Navigation Menu` - Site navigation
- `Menubar` - Application menu bar
- `Breadcrumb` - Navigation breadcrumb
- `Command` - Command palette (⌘K)

### Data Display
- `Table` - Data table
- `Badge` - Status indicator
- `Avatar` - User avatar image
- `Tooltip` - Hover information
- `Hover Card` - Hover preview card
- `Popover` - Floating content
- `Chart` - Data visualization
- `Carousel` - Image/content carousel
- `Aspect Ratio` - Maintain aspect ratio

### Utility
- `Scroll Area` - Custom scrollbar
- `Resizable` - Resizable panels
- `Collapsible` - Collapsible content
- `Toggle` - Toggle button
- `Toggle Group` - Toggle button group

### Custom Components
- `Infinite Moving Cards` - Animated testimonial cards

---

## 🎨 Theme Configuration

### CSS Variables (globals.css)

The theme uses HSL color values defined as CSS custom properties:

```css
:root {
  --background: 0 0% 100%;
  --foreground: 240 10% 3.9%;
  --primary: 240 5.9% 10%;
  --secondary: 240 4.8% 95.9%;
  /* ... more colors */
}

.dark {
  --background: 240 10% 3.9%;
  --foreground: 0 0% 98%;
  --primary: 0 0% 98%;
  --secondary: 240 3.7% 15.9%;
  /* ... more colors */
}
```

### Tailwind Classes

Use semantic color classes that automatically adapt to theme:

```tsx
<div className="bg-background text-foreground">
  <Button className="bg-primary text-primary-foreground">
    Primary Button
  </Button>
  <Card className="bg-card text-card-foreground">
    Card Content
  </Card>
</div>
```

---

## 🎭 Using Animations

### AOS (Animate On Scroll)

```tsx
<div data-aos="fade-up" data-aos-duration="1000">
  This element animates on scroll
</div>
```

AOS is already initialized in `main.tsx` with:
- Duration: 1000ms
- Once: true (animate only once)
- Easing: ease-out

### Framer Motion

```tsx
import { motion } from "framer-motion"

<motion.div
  initial={{ opacity: 0, y: 20 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ duration: 0.5 }}
>
  Animated content
</motion.div>
```

### Custom Keyframes

Infinite scrolling animation (for InfiniteMovingCards):

```tsx
<InfiniteMovingCards
  items={testimonials}
  direction="right"
  speed="slow"
  pauseOnHover={true}
/>
```

---

## 📝 Form Validation Example

Using React Hook Form + Zod:

```tsx
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import * as z from "zod"
import { Form, FormField, FormItem, FormLabel, FormControl, FormMessage } from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"

const formSchema = z.object({
  email: z.string().email("Invalid email address"),
  password: z.string().min(8, "Password must be at least 8 characters"),
})

function LoginForm() {
  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      email: "",
      password: "",
    },
  })

  function onSubmit(values: z.infer<typeof formSchema>) {
    console.log(values)
  }

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
        <FormField
          control={form.control}
          name="password"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Password</FormLabel>
              <FormControl>
                <Input type="password" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit">Sign In</Button>
      </form>
    </Form>
  )
}
```

---

## 🔧 Configuration Files

### vite.config.ts
```typescript
import path from "path"
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: '/ui/',
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  // ... server config
})
```

### tsconfig.app.json
```json
{
  "compilerOptions": {
    // ... other options
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
```

### tailwind.config.ts
```typescript
export default {
  darkMode: ["class"],
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // HSL color variables
      },
      keyframes: {
        "accordion-down": { /* ... */ },
        "accordion-up": { /* ... */ }
      }
    }
  },
  plugins: [require("tailwindcss-animate")]
}
```

### components.json
```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "default",
  "tailwind": {
    "config": "tailwind.config.ts",
    "css": "src/styles/globals.css",
    "cssVariables": true
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui"
  }
}
```

---

## 🎯 Best Practices

### 1. Component Composition
```tsx
// ✅ Good - Compose components
<Card>
  <CardHeader>
    <CardTitle>Title</CardTitle>
    <CardDescription>Description</CardDescription>
  </CardHeader>
  <CardContent>Content</CardContent>
  <CardFooter>
    <Button>Action</Button>
  </CardFooter>
</Card>

// ❌ Avoid - Don't create monolithic components
```

### 2. Use cn() for Conditional Classes
```tsx
import { cn } from "@/lib/utils"

<Button className={cn(
  "base-styles",
  isActive && "active-styles",
  isDisabled && "disabled-styles"
)} />
```

### 3. Leverage Variants
```tsx
<Button variant="default">Default</Button>
<Button variant="destructive">Delete</Button>
<Button variant="outline">Cancel</Button>
<Button variant="ghost">Ghost</Button>
<Button size="sm">Small</Button>
<Button size="lg">Large</Button>
```

### 4. Accessible Components
All shadcn/ui components follow WAI-ARIA guidelines:
- Proper ARIA labels
- Keyboard navigation
- Focus management
- Screen reader support

---

## 🐛 Troubleshooting

### Issue: Path aliases not working
**Solution**: Restart your dev server after updating tsconfig.json

### Issue: Tailwind classes not applying
**Solution**: Check that globals.css is imported in main.tsx

### Issue: Dark mode not toggling
**Solution**: Ensure ThemeProvider wraps your app with `attribute="class"`

### Issue: Components not styled correctly
**Solution**: Verify CSS variables are defined in globals.css for both :root and .dark

---

## 📦 Dependencies Installed

### Runtime Dependencies (40+)
- All Radix UI primitives (@radix-ui/react-*)
- Form libraries (react-hook-form, zod, @hookform/resolvers)
- Animations (framer-motion, aos)
- UI utilities (class-variance-authority, clsx, tailwind-merge, cmdk)
- Icons (lucide-react)
- Theme (next-themes)
- Date handling (date-fns, react-day-picker)
- Charts (recharts)
- Carousels (embla-carousel-react)
- Notifications (sonner, react-hot-toast)
- And more...

### Dev Dependencies
- tailwindcss@^3.4.17
- postcss@^8
- autoprefixer@^10.4.20
- @types/aos@^3.0.7

---

## 🎉 What's Next?

1. **Explore the showcase**: Visit `/showcase` to see all components
2. **Customize colors**: Edit CSS variables in `globals.css`
3. **Add more components**: Run `npx shadcn@latest add <component-name>`
4. **Migrate existing components**: Gradually replace old styles with Tailwind
5. **Build new features**: Use the component library for rapid development

---

## 📚 Resources

- [shadcn/ui Documentation](https://ui.shadcn.com)
- [Tailwind CSS Docs](https://tailwindcss.com)
- [Radix UI Docs](https://radix-ui.com)
- [Framer Motion Docs](https://www.framer.com/motion)
- [React Hook Form Docs](https://react-hook-form.com)
- [Zod Documentation](https://zod.dev)

---

## ✅ Setup Verification Checklist

- [x] All 44+ shadcn/ui components installed
- [x] Tailwind CSS configured with theme variables
- [x] Dark/light mode working with toggle
- [x] Path aliases (@/) configured
- [x] TypeScript compilation successful
- [x] Build process working
- [x] Dev server running on http://localhost:5173/ui/
- [x] Inter font loaded from Google Fonts
- [x] AOS animations initialized
- [x] Framer Motion available
- [x] Form validation (React Hook Form + Zod) ready
- [x] Custom components (InfiniteMovingCards) created
- [x] Theme toggle component working
- [x] Component showcase page created

**🎊 Your complete UI theme system is ready to use!**
