import { Link } from "react-router-dom";
import { useEffect } from "react";
import AOS from 'aos';
import 'aos/dist/aos.css';

export function Footer() {
  useEffect(() => {
    AOS.init({
      duration: 800,
      easing: 'ease-in-out',
      once: true,
      offset: 50,
    });
  }, []);

  return (
    <footer className="border-t border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container mx-auto px-6 py-12">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          {/* Company Info */}
          <div className="space-y-4" data-aos="fade-up" data-aos-delay="0">
            <h3 className="text-lg font-bold">Fluid MCP </h3>
            <p className="text-sm text-muted-foreground">
              A secure, vetted registry of Model Context Protocol Packages for agentic AI solutions. Building the future of AI integration.
            </p>
            <div className="flex space-x-4">
              <a
                href="https://x.com/fluidAI1"
                target="_blank"
                rel="noopener noreferrer"
                className="text-muted-foreground hover:text-foreground transition-colors"
              >
                <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
                </svg>
              </a>
              <a
                href="https://www.linkedin.com/company/fluid-ai/posts/?feedView=all"
                target="_blank"
                rel="noopener noreferrer"
                className="text-muted-foreground hover:text-foreground transition-colors"
              >
                <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
                </svg>
              </a>
            </div>
          </div>

          {/* Registry */}
          <div className="space-y-4" data-aos="fade-up" data-aos-delay="100">
            <h4 className="text-sm font-semibold">Registry</h4>
            <ul className="space-y-2 text-sm">
              <li>
                <Link to="/servers" className="text-muted-foreground hover:text-foreground transition-colors">
                  Browse Servers
                </Link>
              </li>
              <li>
                <Link to="/servers" className="text-muted-foreground hover:text-foreground transition-colors">
                  Featured Packages
                </Link>
              </li>
              <li>
                <Link to="/servers/manage" className="text-muted-foreground hover:text-foreground transition-colors">
                  Submit Package
                </Link>
              </li>
              <li>
                <a href="https://www.fluid.ai/contact-us" target="_blank" rel="noopener noreferrer" className="text-muted-foreground hover:text-foreground transition-colors">
                  Report Issue
                </a>
              </li>
            </ul>
          </div>

          {/* Documentation */}
          <div className="space-y-4" data-aos="fade-up" data-aos-delay="200">
            <h4 className="text-sm font-semibold">Documentation</h4>
            <ul className="space-y-2 text-sm">
              <li>
                <Link to="/documentation#getting-started" className="text-muted-foreground hover:text-foreground transition-colors">
                  Getting Started
                </Link>
              </li>
              <li>
                <Link to="/documentation#using-fluidai-mcp" className="text-muted-foreground hover:text-foreground transition-colors">
                  Integration Guide
                </Link>
              </li>
              <li>
                <Link to="/documentation#available-endpoints" className="text-muted-foreground hover:text-foreground transition-colors">
                  API Reference
                </Link>
              </li>
              <li>
                <Link to="/documentation#troubleshooting" className="text-muted-foreground hover:text-foreground transition-colors">
                  Best Practices
                </Link>
              </li>
            </ul>
          </div>

          {/* Community */}
          <div className="space-y-4" data-aos="fade-up" data-aos-delay="300">
            <h4 className="text-sm font-semibold">Community</h4>
            <ul className="space-y-2 text-sm">
              <li>
                <a href="https://x.com/fluidAI1" target="_blank" rel="noopener noreferrer" className="text-muted-foreground hover:text-foreground transition-colors">
                  Twitter
                </a>
              </li>
              <li>
                <a href="https://www.linkedin.com/company/fluid-ai/" target="_blank" rel="noopener noreferrer" className="text-muted-foreground hover:text-foreground transition-colors">
                  LinkedIn
                </a>
              </li>
            </ul>
          </div>
        </div>

        {/* Copyright */}
        <div className="mt-12 pt-8 border-t border-border/40 text-center text-sm text-muted-foreground">
          <p>© 2026 Fluid MCP. All rights reserved.</p>
          <p className="mt-2">Your Path to Unstoppable Success!</p>
        </div>
      </div>
    </footer>
  );
}
