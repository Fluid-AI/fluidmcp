import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { ThemeToggle } from "@/components/theme-toggle"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Calendar } from "@/components/ui/calendar"
import { useState } from "react"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { AlertCircle, Check } from "lucide-react"
import { Progress } from "@/components/ui/progress"
import { Separator } from "@/components/ui/separator"
import { Switch } from "@/components/ui/switch"
import { Slider } from "@/components/ui/slider"
import { InfiniteMovingCards } from "@/components/ui/infinite-moving-cards"

const testimonials = [
  {
    quote: "This is an amazing product! It has transformed the way we work.",
    name: "John Doe",
    title: "CEO at Tech Corp",
  },
  {
    quote: "Highly recommend to everyone. Best investment we've made this year.",
    name: "Jane Smith",
    title: "Designer at Studio X",
  },
  {
    quote: "Changed the way we work. Incredible performance and reliability.",
    name: "Bob Johnson",
    title: "Developer at StartupCo",
  },
  {
    quote: "Outstanding support and features. Worth every penny!",
    name: "Alice Williams",
    title: "Product Manager at BigTech",
  },
]

export default function ComponentShowcase() {
  const [date, setDate] = useState<Date | undefined>(new Date())
  const [progress] = useState(45)

  return (
    <div className="container mx-auto p-8 space-y-12">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-bold mb-2">shadcn/ui Component Showcase</h1>
          <p className="text-muted-foreground">
            Complete design system with 44+ components, Tailwind CSS, and dark mode
          </p>
        </div>
        <ThemeToggle />
      </div>

      <Separator />

      {/* Buttons Section */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Buttons</h2>
        <div className="flex flex-wrap gap-4">
          <Button>Default</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="destructive">Destructive</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="link">Link</Button>
        </div>
        <div className="flex flex-wrap gap-4">
          <Button size="sm">Small</Button>
          <Button size="default">Default</Button>
          <Button size="lg">Large</Button>
          <Button size="icon">
            <Check className="h-4 w-4" />
          </Button>
        </div>
      </section>

      <Separator />

      {/* Badges Section */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Badges</h2>
        <div className="flex flex-wrap gap-4">
          <Badge>Default</Badge>
          <Badge variant="secondary">Secondary</Badge>
          <Badge variant="destructive">Destructive</Badge>
          <Badge variant="outline">Outline</Badge>
        </div>
      </section>

      <Separator />

      {/* Cards Section */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Cards</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Card Title</CardTitle>
              <CardDescription>Card description goes here</CardDescription>
            </CardHeader>
            <CardContent>
              <p>This is the card content area. You can put anything here.</p>
            </CardContent>
            <CardFooter>
              <Button>Action</Button>
            </CardFooter>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Another Card</CardTitle>
              <CardDescription>With different content</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-sm">Progress</span>
                  <span className="text-sm font-medium">{progress}%</span>
                </div>
                <Progress value={progress} />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Settings Card</CardTitle>
              <CardDescription>Toggle your preferences</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <Label htmlFor="notifications">Notifications</Label>
                <Switch id="notifications" />
              </div>
              <div className="flex items-center justify-between">
                <Label htmlFor="dark-mode">Dark Mode</Label>
                <Switch id="dark-mode" defaultChecked />
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      <Separator />

      {/* Alerts Section */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Alerts</h2>
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Heads up!</AlertTitle>
          <AlertDescription>
            You can add components to your app using the cli.
          </AlertDescription>
        </Alert>
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>
            Your session has expired. Please log in again.
          </AlertDescription>
        </Alert>
      </section>

      <Separator />

      {/* Tabs Section */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Tabs</h2>
        <Tabs defaultValue="account" className="w-full">
          <TabsList>
            <TabsTrigger value="account">Account</TabsTrigger>
            <TabsTrigger value="password">Password</TabsTrigger>
            <TabsTrigger value="settings">Settings</TabsTrigger>
          </TabsList>
          <TabsContent value="account" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Account</CardTitle>
                <CardDescription>
                  Make changes to your account here.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="space-y-1">
                  <Label htmlFor="name">Name</Label>
                  <Input id="name" defaultValue="John Doe" />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="username">Username</Label>
                  <Input id="username" defaultValue="@johndoe" />
                </div>
              </CardContent>
              <CardFooter>
                <Button>Save changes</Button>
              </CardFooter>
            </Card>
          </TabsContent>
          <TabsContent value="password">
            <Card>
              <CardHeader>
                <CardTitle>Password</CardTitle>
                <CardDescription>
                  Change your password here.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="space-y-1">
                  <Label htmlFor="current">Current password</Label>
                  <Input id="current" type="password" />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="new">New password</Label>
                  <Input id="new" type="password" />
                </div>
              </CardContent>
              <CardFooter>
                <Button>Save password</Button>
              </CardFooter>
            </Card>
          </TabsContent>
          <TabsContent value="settings">
            <Card>
              <CardHeader>
                <CardTitle>Settings</CardTitle>
                <CardDescription>
                  Manage your application settings.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>Volume</Label>
                  <Slider defaultValue={[50]} max={100} step={1} />
                </div>
                <div className="space-y-2">
                  <Label>Brightness</Label>
                  <Slider defaultValue={[75]} max={100} step={1} />
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </section>

      <Separator />

      {/* Accordion Section */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Accordion</h2>
        <Accordion type="single" collapsible className="w-full">
          <AccordionItem value="item-1">
            <AccordionTrigger>Is it accessible?</AccordionTrigger>
            <AccordionContent>
              Yes. It adheres to the WAI-ARIA design pattern and is fully accessible.
            </AccordionContent>
          </AccordionItem>
          <AccordionItem value="item-2">
            <AccordionTrigger>Is it styled?</AccordionTrigger>
            <AccordionContent>
              Yes. It comes with default styles that matches the other components'
              aesthetic.
            </AccordionContent>
          </AccordionItem>
          <AccordionItem value="item-3">
            <AccordionTrigger>Is it animated?</AccordionTrigger>
            <AccordionContent>
              Yes. It's animated by default, but you can disable it if you prefer.
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </section>

      <Separator />

      {/* Calendar Section */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Calendar</h2>
        <div className="flex justify-center">
          <Calendar
            mode="single"
            selected={date}
            onSelect={setDate}
            className="rounded-md border"
          />
        </div>
      </section>

      <Separator />

      {/* Infinite Moving Cards Section */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Infinite Moving Cards</h2>
        <div className="relative flex flex-col items-center justify-center overflow-hidden rounded-lg border bg-background py-8">
          <InfiniteMovingCards
            items={testimonials}
            direction="right"
            speed="slow"
          />
        </div>
      </section>

      <Separator />

      {/* Footer */}
      <footer className="text-center text-muted-foreground pb-8">
        <p>✅ Complete shadcn/ui setup with 44+ components</p>
        <p>✅ Tailwind CSS with dark/light theme support</p>
        <p>✅ Framer Motion, AOS animations, and custom keyframes</p>
        <p className="mt-4 font-semibold">Theme system fully configured!</p>
      </footer>
    </div>
  )
}
