import { Link } from "react-router-dom";
import { BackgroundLines } from "@/components/ui/background-lines";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Footer } from "@/components/Footer";
import { InfiniteMovingCards } from "@/components/ui/infinite-moving-cards";

const testimonials = [
  {
    quote:
      "Fluid MCP Registry has completely transformed how we integrate AI tools into our workflow. The security guarantees give us peace of mind.",
    name: "Sarah Chen",
    title: "CTO at TechFlow AI",
  },
  {
    quote:
      "The quality of MCP servers in this registry is unmatched. Every package is thoroughly vetted, which saves us countless hours of security audits.",
    name: "Michael Rodriguez",
    title: "Lead AI Engineer at DataSync",
  },
  {
    quote:
      "As a developer, I appreciate how easy it is to discover and integrate new MCP servers. The documentation is top-notch and the API is intuitive.",
    name: "Emily Watson",
    title: "Full Stack Developer at CloudNine",
  },
  {
    quote:
      "We've built our entire AI infrastructure on MCP servers from this registry. The reliability and security standards are exactly what enterprise needs.",
    name: "David Park",
    title: "VP of Engineering at Enterprise AI Solutions",
  },
  {
    quote:
      "The community around Fluid MCP Registry is incredible. It's not just a registry, it's a movement towards safer AI integration.",
    name: "Lisa Thompson",
    title: "AI Research Lead at InnovateLabs",
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="fixed top-0 w-full z-50 border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container mx-auto flex h-16 items-center justify-between px-6">
          <Link to="/" className="flex items-center space-x-2">
            <span className="text-xl font-bold">Fluid MCP </span>
          </Link>
          <nav className="hidden md:flex items-center space-x-6 text-sm">
            <Link to="/" className="transition-colors hover:text-foreground/80 text-foreground">
              Home
            </Link>
            <Link to="/servers" className="transition-colors hover:text-foreground/80 text-foreground/60">
              Servers
            </Link>
            <a href="#" className="transition-colors hover:text-foreground/80 text-foreground/60">
              Submit
            </a>
            <a href="#" className="transition-colors hover:text-foreground/80 text-foreground/60">
              Documentation
            </a>
          </nav>
          <div className="flex items-center space-x-4">
            <Button variant="ghost" size="sm" asChild>
              <Link to="/servers">Browse Registry</Link>
            </Button>
          </div>
        </div>
      </header>

      {/* Hero Section with Background Lines */}
      <main className="flex-1 pt-16">
        <BackgroundLines className="!h-auto w-full flex items-center justify-center relative py-16">
          <div className="container mx-auto px-6 relative z-10">
            <div className="flex flex-col items-center justify-center text-center space-y-4">
              {/* Badge */}
              <Badge variant="secondary" className="px-4 py-1 text-sm">
                Trusted MCP Registry
              </Badge>

              {/* Main Heading */}
              <h1 className="text-4xl md:text-6xl lg:text-7xl font-bold tracking-tight max-w-5xl">
                Run MCP Servers with Uncompromising Security
              </h1>

              {/* Subheading */}
              <p className="text-lg md:text-xl text-muted-foreground max-w-3xl">
                Your sanctuary for secure, vetted Model Context Protocol packages that empower your agentic AI solutions
              </p>

              {/* CTA Buttons */}
              <div className="flex flex-col sm:flex-row gap-4 pt-2">
                <Button size="lg" asChild>
                  <Link to="/servers">Browse Registry</Link>
                </Button>
                <Button size="lg" variant="outline" asChild>
                  <a href="#">Submit Package</a>
                </Button>
              </div>
            </div>
          </div>
        </BackgroundLines>

        {/* Testimonials Section */}
        <div className="py-6 bg-background">
          <div className="container mx-auto px-6">
            <h2 className="text-2xl md:text-3xl font-bold text-center mb-2">
              Trusted by Developers Worldwide
            </h2>
            <p className="text-center text-muted-foreground mb-6 max-w-2xl mx-auto">
              Join thousands of developers building the future of AI with secure MCP servers
            </p>
            <InfiniteMovingCards
              items={testimonials}
              direction="right"
              speed="slow"
            />
          </div>
        </div>
      </main>

      {/* Footer */}
      <Footer />
    </div>
  );
}
