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
        <BackgroundLines className="min-h-[calc(100vh-4rem)] w-full flex items-center justify-center relative">
          <div className="container mx-auto px-6 py-20 relative z-10">
            <div className="flex flex-col items-center justify-center text-center space-y-8">
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
              <div className="flex flex-col sm:flex-row gap-4 pt-4">
                <Button size="lg" asChild>
                  <Link to="/servers">Browse Registry</Link>
                </Button>
                <Button size="lg" variant="outline" asChild>
                  <a href="#">Submit Package</a>
                </Button>
              </div>
            </div>

            {/* Why Choose Section */}
            <div className="mt-32 relative z-10">

              <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mt-12">
                {/* Feature 1 */}
                <div className="p-6 rounded-lg border border-border/40 bg-card/50 backdrop-blur">
                  <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mb-4">
                    <svg className="w-6 h-6 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                    </svg>
                  </div>
                  <h3 className="text-xl font-semibold mb-2">Vetted Security</h3>
                  <p className="text-muted-foreground">
                    Every package is thoroughly reviewed and tested to ensure the highest security standards
                  </p>
                </div>

                {/* Feature 2 */}
                <div className="p-6 rounded-lg border border-border/40 bg-card/50 backdrop-blur">
                  <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mb-4">
                    <svg className="w-6 h-6 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                  </div>
                  <h3 className="text-xl font-semibold mb-2">Fast Integration</h3>
                  <p className="text-muted-foreground">
                    Get up and running in minutes with our comprehensive documentation and examples
                  </p>
                </div>

                {/* Feature 3 */}
                <div className="p-6 rounded-lg border border-border/40 bg-card/50 backdrop-blur">
                  <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mb-4">
                    <svg className="w-6 h-6 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                    </svg>
                  </div>
                  <h3 className="text-xl font-semibold mb-2">Community Driven</h3>
                  <p className="text-muted-foreground">
                    Built by the community, for the community. Contribute and help shape the future
                  </p>
                </div>
              </div>
            </div>
          </div>
        </BackgroundLines>

        {/* Testimonials Section */}
        <div className="py-20 bg-background">
          <div className="container mx-auto px-6">
            <h2 className="text-3xl md:text-4xl font-bold text-center mb-4">
              Trusted by Developers Worldwide
            </h2>
            <p className="text-center text-muted-foreground text-lg mb-12 max-w-2xl mx-auto">
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
