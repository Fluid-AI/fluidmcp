"use client"

import React, { useState, useEffect } from "react"
import { Link, useLocation } from "react-router-dom"
import {
  ChevronDown,
  ChevronRight,
  Code,
  FileJson,
  Server,
  Package,
  ChevronRightCircle,
  HelpCircle,
  BookOpen,
  Key,
  AlertCircle,
  Zap,
  Rocket,
  Wrench,
  FileText,
  List,
  Search,
  Copy,
  CheckCircle,
  ArrowUp,
  Home,
  Menu,
  X,
  PanelLeft,
  PanelLeftClose
} from "lucide-react"
import { Footer } from "@/components/Footer"

// Sidebar navigation structure
const sidebarGroups = [
  {
    title: "Introduction",
    items: [
      { id: "fluidai-mcp-installer", label: "FluidAI MCP Installer", icon: <FileText className="h-4 w-4" /> },
      { id: "what-is-mcp", label: "What is MCP", icon: <HelpCircle className="h-4 w-4" /> },
      { id: "getting-started", label: "Getting Started", icon: <Rocket className="h-4 w-4" /> },
    ]
  },
  {
    title: "Setup",
    items: [
      { id: "prerequisites", label: "Prerequisites", icon: <CheckCircle className="h-4 w-4" /> },
      { id: "installation", label: "Installation", icon: <Package className="h-4 w-4" /> },
    ]
  },
  {
    title: "Usage",
    items: [
      { id: "using-fluidai-mcp", label: "Using the FluidAI MCP Installer", icon: <Wrench className="h-4 w-4" /> },
      { id: "installing-server", label: "Installing an MCP Server", icon: <Server className="h-4 w-4" /> },
      { id: "running-installed", label: "Running an Installed Package", icon: <Zap className="h-4 w-4" /> },
      { id: "listing-packages", label: "Listing Installed Packages", icon: <List className="h-4 w-4" /> },
      { id: "alternative-commands", label: "Alternative Commands", icon: <Code className="h-4 w-4" /> },
    ]
  },
  {
    title: "API",
    items: [
      { id: "api-access-fastapi", label: "API Access via FastAPI", icon: <Server className="h-4 w-4" /> },
      { id: "available-endpoints", label: "Available API Endpoints", icon: <FileJson className="h-4 w-4" /> },
      { id: "example-call", label: "Example API Call", icon: <Code className="h-4 w-4" /> },
      { id: "managing-keys", label: "Managing API Keys", icon: <Key className="h-4 w-4" /> },
    ]
  },
  {
    title: "Support",
    items: [
      { id: "troubleshooting", label: "Troubleshooting", icon: <AlertCircle className="h-4 w-4" /> },
      { id: "common-issues", label: "Common Issues and Solutions", icon: <HelpCircle className="h-4 w-4" /> },
      { id: "faq", label: "FAQ", icon: <HelpCircle className="h-4 w-4" /> },
    ]
  }
]

// Badge Component
const Badge: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = "" }) => (
  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${className}`}>
    {children}
  </span>
)

// Card Components
const Card: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = "" }) => (
  <div className={`rounded-lg border bg-transparent text-card-foreground shadow-sm ${className}`}>
    {children}
  </div>
)

const CardHeader: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = "" }) => (
  <div className={`flex flex-col space-y-1.5 p-6 ${className}`}>
    {children}
  </div>
)

const CardTitle: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = "" }) => (
  <h3 className={`font-semibold leading-none tracking-tight ${className}`}>
    {children}
  </h3>
)

const CardContent: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = "" }) => (
  <div className={`p-6 pt-0 ${className}`}>
    {children}
  </div>
)

// Code Block Component with copy functionality
const CodeBlock: React.FC<{ children: string; language?: string }> = ({ children, language = "bash" }) => {
  const [copied, setCopied] = useState(false)
  
  const handleCopy = () => {
    navigator.clipboard.writeText(children)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  
  return (
    <div className="relative group w-full overflow-hidden">
      <div className="absolute right-2 top-2 z-10">
        <button 
          onClick={handleCopy}
          className="bg-[#2A2D36] hover:bg-[#34373F] text-white p-2 rounded-md transition-colors"
          aria-label="Copy code"
        >
          {copied ? <CheckCircle className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
        </button>
      </div>
      <div style={{ backgroundColor: 'hsl(240, 10%, 3.9%)' }} className={`text-gray-200 p-4 rounded-md font-mono text-sm leading-relaxed overflow-x-auto w-full border border-[#2A2D36] ${language}`}>
        {children}
      </div>
    </div>
  )
}

// Utility function for class names
const cn = (...classes: (string | boolean | undefined)[]) => {
  return classes.filter(Boolean).join(' ')
}

export default function Documentation() {
  const location = useLocation()
  const [activeItem, setActiveItem] = useState("fluidai-mcp-installer")
  const [searchTerm, setSearchTerm] = useState("")
  const [expandedGroups, setExpandedGroups] = useState<string[]>(["Introduction"])
  const [showScrollTop, setShowScrollTop] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  
  // Track scroll position for "scroll to top" button
  useEffect(() => {
    const handleScroll = () => {
      setShowScrollTop(window.scrollY > 400)
    }
    
    window.addEventListener('scroll', handleScroll)
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  // Close mobile sidebar when window resizes to desktop
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth >= 768) {
        setMobileSidebarOpen(false)
      }
    }

    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  // Handle URL hash navigation - React Router location changes
  useEffect(() => {
    const hash = location.hash.replace('#', '')
    if (!hash) return

    const allItems = sidebarGroups.flatMap(group => group.items)
    const matchingItem = allItems.find(item => item.id === hash)

    if (matchingItem) {
      setActiveItem(hash)

      const group = sidebarGroups.find(g =>
        g.items.some(item => item.id === hash)
      )

      if (group) {
        setExpandedGroups(prev =>
          prev.includes(group.title) ? prev : [...prev, group.title]
        )
      }

      // Scroll to top after React renders the new section
      setTimeout(() => {
        window.scrollTo({ top: 0, behavior: "smooth" })
      }, 50)
    }
  }, [location.hash])

  // Handle native browser hashchange events (fallback for same-page navigation)
  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.replace('#', '')
      if (!hash) return

      const allItems = sidebarGroups.flatMap(group => group.items)
      const matchingItem = allItems.find(item => item.id === hash)

      if (matchingItem) {
        setActiveItem(hash)

        const group = sidebarGroups.find(g =>
          g.items.some(item => item.id === hash)
        )

        if (group) {
          setExpandedGroups(prev =>
            prev.includes(group.title) ? prev : [...prev, group.title]
          )
        }

        // Scroll to top after React renders the new section
        setTimeout(() => {
          window.scrollTo({ top: 0, behavior: "smooth" })
        }, 50)
      }
    }

    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])
  
  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const toggleSidebar = () => {
    setSidebarOpen(!sidebarOpen)
  }

  const toggleMobileSidebar = () => {
    setMobileSidebarOpen(!mobileSidebarOpen)
  }

  const handleGroupToggle = (groupTitle: string) => {
    setExpandedGroups(prev => 
      prev.includes(groupTitle) 
        ? prev.filter(g => g !== groupTitle) 
        : [...prev, groupTitle]
    )
  }

  const handleItemClick = (item: string) => {
    // Update URL hash - this will trigger the hashchange event which handles everything
    window.location.hash = item

    // Close mobile sidebar after item selection on mobile
    if (window.innerWidth < 768) {
      setMobileSidebarOpen(false)
    }
  }
  
  // Filter sidebar items based on search term
  const filteredGroups = searchTerm 
    ? sidebarGroups.map(group => ({
        ...group,
        items: group.items.filter(item => 
          item.label.toLowerCase().includes(searchTerm.toLowerCase())
        )
      })).filter(group => group.items.length > 0)
    : sidebarGroups
  
  const getActiveItemGroup = () => {
    for (const group of sidebarGroups) {
      if (group.items.some(item => item.id === activeItem)) {
        return group.title
      }
    }
    return null
  }
  
  // Create breadcrumb navigation
  const activeItemData = sidebarGroups
    .flatMap(group => group.items)
    .find(item => item.id === activeItem)
  
  const activeItemGroup = getActiveItemGroup()
 
  return (
    <div className="min-h-screen bg-background flex flex-col text-sm" style={{ backgroundColor: 'hsl(240, 10%, 3.9%)' }}>
      {/* Header - Same as Dashboard */}
      <header className="fixed top-0 left-0 right-0 z-50 border-b border-border/40 bg-background/95 backdrop-blur-md supports-[backdrop-filter]:bg-background/60 transition-all duration-200">
        {/* Mobile menu button - fixed position to not affect header layout */}
        <button
          onClick={toggleMobileSidebar}
          className="fixed left-4 top-4 md:hidden h-8 w-8 flex items-center justify-center rounded-md hover:bg-zinc-800 text-white z-[60]"
          aria-label="Toggle sidebar menu"
        >
          <Menu className="h-5 w-5" />
        </button>

        <div className="container mx-auto flex h-16 max-w-screen-xl items-center justify-between px-6">
          <div className="flex items-center space-x-8">
            <Link to="/" className="flex items-center space-x-2 group transition-all duration-200 hover:scale-105">
              <span className="text-lg font-bold bg-gradient-to-r from-foreground to-foreground/80 bg-clip-text whitespace-nowrap">Fluid MCP </span>
            </Link>
            <nav className="hidden md:flex items-center space-x-1 text-sm">
              <Link 
                to="/servers" 
                className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground/60"
              >
                Servers
              </Link>
              <Link 
                to="/status" 
                className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground/60"
              >
                Status
              </Link>
              <Link 
                to="/documentation" 
                className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground"
              >
                Documentation
              </Link>
            </nav>
          </div>
          <div className="flex items-center space-x-3">
            <button 
              style={{ background: '#000', color: '#fff', border: 'none', padding: '0.5rem 1rem', borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '500', display: 'inline-flex', alignItems: 'center', transition: 'all 0.2s', margin: 0 }}
              onMouseEnter={(e) => e.currentTarget.style.background = '#18181b'}
              onMouseLeave={(e) => e.currentTarget.style.background = '#000'}
            >
              <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
              </svg>
              Fluid MCP for your Enterprise
            </button>
            <button 
              style={{ background: '#000', color: '#fff', border: 'none', padding: '0.5rem 1rem', borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '500', display: 'inline-flex', alignItems: 'center', transition: 'all 0.2s', margin: 0 }}
              onMouseEnter={(e) => e.currentTarget.style.background = '#18181b'}
              onMouseLeave={(e) => e.currentTarget.style.background = '#000'}
            >
              <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
              </svg>
              Report Issue
            </button>
          </div>
        </div>
      </header>

      {/* Dashboard Content with proper padding for fixed header */}
      <div style={{ paddingTop: '64px' }} className="max-w-screen-2xl mx-auto w-full flex-grow flex flex-col md:flex-row">
        {/* Mobile sidebar overlay */}
        {mobileSidebarOpen && (
          <div 
            className="fixed inset-0 bg-black/80 backdrop-blur-sm z-40 md:hidden"
            onClick={() => setMobileSidebarOpen(false)}
          />
        )}

        {/* Sidebar Navigation */}
        <aside 
          style={{ backgroundColor: 'hsl(240, 10%, 3.9%)' }}
          className={cn(
            "fixed md:sticky md:top-16 z-40 md:z-0 inset-y-0 left-0 h-full md:h-[calc(100vh-4rem)] w-3/4 sm:max-w-64 border-r border-[#1F2228] transform transition-transform duration-200 ease-in-out overflow-y-auto md:transform-none",
            mobileSidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
            sidebarOpen ? "md:w-64" : "md:w-16"
          )}
        >
          <div className="p-4 pb-12 space-y-4">
            <div className="flex flex-col space-y-1">
              <div className={cn(
                "flex items-center",
                sidebarOpen ? "justify-between" : "md:justify-center"
              )}>
                {sidebarOpen && (
                  <div className="font-medium text-base text-white">
                    Documentation
                  </div>
                )}
                <div className="flex items-center">
                  {/* Mobile close button */}
                  <button
                    onClick={toggleMobileSidebar}
                    className="h-8 w-8 flex md:hidden items-center justify-center rounded-md hover:bg-[#1A1D26] text-white"
                    aria-label="Close sidebar menu"
                  >
                    <X className="h-5 w-5" />
                  </button>

                  {/* Desktop sidebar toggle */}
                  <button
                    onClick={toggleSidebar}
                    className="h-8 w-8 hidden md:flex items-center justify-center rounded-md hover:bg-[#1A1D26] text-white"
                    aria-label={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
                  >
                    {sidebarOpen ?
                      <PanelLeftClose className="h-5 w-5" /> :
                      <PanelLeft className="h-5 w-5" />
                    }
                  </button>
                </div>
              </div>
              
              {/* Search Bar */}
              {sidebarOpen && (
                <div className="relative mt-2">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-3.5 w-3.5 text-gray-500" />
                  <input
                    type="text"
                    placeholder="Search servers..."
                    className="w-full rounded-md border border-[#2A2D36] bg-[#1A1D26] px-8 py-2 text-sm text-white placeholder:text-gray-500 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-600"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                  />
                  {searchTerm && (
                    <button 
                      onClick={() => setSearchTerm("")}
                      className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-500 hover:text-white"
                    >
                      ×
                    </button>
                  )}
                </div>
              )}
            </div>
            
            {/* Grouped Sidebar Items */}
            <div className="space-y-0.5">
              {filteredGroups.map((group) => (
                <div key={group.title} className="mb-1">
                  {sidebarOpen ? (
                    <div 
                      className="flex items-center justify-between py-2 px-2 text-xs font-semibold text-gray-400 hover:text-white cursor-pointer"
                      onClick={() => handleGroupToggle(group.title)}
                    >
                      <span>{group.title}</span>
                      {expandedGroups.includes(group.title) ? 
                        <ChevronDown className="h-3.5 w-3.5" /> : 
                        <ChevronRight className="h-3.5 w-3.5" />
                      }
                    </div>
                  ) : (
                    <div className="flex justify-center py-2">
                      <div className="h-px w-8 bg-[#1F2228]"></div>
                    </div>
                  )}
                  
                  {(sidebarOpen && expandedGroups.includes(group.title) || !sidebarOpen) && (
                    <div className={cn(
                      "space-y-0.5",
                      sidebarOpen ? "mt-0.5 ml-2 border-l border-[#1F2228] pl-2" : "flex flex-col items-center"
                    )}>
                      {group.items.map((item) => (
                        <div
                          key={item.id}
                          className={cn(
                            "flex items-center rounded-md cursor-pointer transition-colors",
                            activeItem === item.id 
                              ? "bg-[#1A1D26] text-white font-medium" 
                              : "hover:bg-[#1A1D26]/50 text-gray-400 hover:text-white",
                            sidebarOpen ? "py-2 px-3 text-sm" : "p-2 justify-center"
                          )}
                          onClick={() => handleItemClick(item.id)}
                          title={!sidebarOpen ? item.label : undefined}
                        >
                          {item.icon && <span className={sidebarOpen ? "mr-2" : ""}>{item.icon}</span>}
                          {sidebarOpen && <span>{item.label}</span>}
                          {sidebarOpen && activeItem === item.id && <ChevronRightCircle className="ml-auto h-3.5 w-3.5" />}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </aside>
       
        {/* Main Content Area */}
        <main className={cn(
          "flex-grow w-full px-4 py-6 md:px-8 pb-12 overflow-x-hidden",
          sidebarOpen ? "md:pl-8" : "md:pl-6",
          sidebarOpen ? "md:w-[calc(100%-16rem)]" : "md:w-[calc(100%-4rem)]"
        )}>
          {/* Breadcrumb navigation */}
          {activeItemData && (
            <nav className="flex mb-6 text-sm text-gray-400 w-full overflow-hidden">
              <div className="flex items-center truncate">
                <Home className="h-4 w-4 mr-2 flex-shrink-0" />
                <span className="mx-2">/</span>
                {activeItemGroup && (
                  <>
                    <span className="truncate">{activeItemGroup}</span>
                    <span className="mx-2 flex-shrink-0">/</span>
                  </>
                )}
                <span className="font-medium text-white truncate">{activeItemData.label}</span>
              </div>
            </nav>
          )}

          {/* FluidAI MCP Installer */}
          {activeItem === "fluidai-mcp-installer" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">Documentation</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">FluidAI MCP Installer</h1>
               
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  A user-friendly command-line tool designed to help you install, manage, and run Model Context Protocol (MCP) servers effortlessly.
                </p>
              </div>
             
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
                <Card className="border border-[#2A2D36] bg-transparent hover:border-gray-600 transition-colors hover:shadow-lg">
                  <CardHeader className="pb-3 pt-5">
                    <CardTitle className="flex items-center gap-2 text-lg text-white">
                      <Package className="h-5 w-5 text-blue-400" />
                      Install MCP Servers
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3 text-sm text-gray-300">
                    <p>
                      Install MCP packages from the registry or other sources with a simple command
                    </p>
                    <div className="pt-2">
                      <button 
                        className="bg-white text-black hover:bg-gray-100 px-4 py-2 rounded-md text-sm font-medium transition-colors"
                        onClick={() => handleItemClick("installation")}
                      >
                        View Installation Guide
                      </button>
                    </div>
                  </CardContent>
                </Card>
               
                <Card className="border border-[#2A2D36] bg-transparent hover:border-gray-600 transition-colors hover:shadow-lg">
                  <CardHeader className="pb-3 pt-5">
                    <CardTitle className="flex items-center gap-2 text-lg text-white">
                      <Rocket className="h-5 w-5 text-blue-400" />
                      Run MCP Servers
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3 text-sm text-gray-300">
                    <p>
                      Easily run and manage installed MCP servers with customizable options
                    </p>
                    <div className="pt-2">
                      <button 
                        className="bg-white text-black hover:bg-gray-100 px-4 py-2 rounded-md text-sm font-medium transition-colors"
                        onClick={() => handleItemClick("running-installed")}
                      >
                        View Running Guide
                      </button>
                    </div>
                  </CardContent>
                </Card>
              </div>
              
              <div className="mt-8 border-t border-[#1F2228] pt-6">
                <h2 className="text-2xl font-bold mb-4 text-white">What's Next?</h2>
                <p className="mb-5 text-sm text-gray-300">Ready to get started? Check out the following resources:</p>
                
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div onClick={() => handleItemClick("what-is-mcp")} className="border border-[#2A2D36] bg-transparent rounded-lg p-5 hover:border-blue-500 hover:shadow-lg cursor-pointer transition-all">
                    <div className="flex flex-col items-center text-center">
                      <HelpCircle className="h-8 w-8 text-blue-400 mb-3" />
                      <h3 className="font-medium text-base text-white mb-2">Learn About MCP</h3>
                      <p className="text-sm text-gray-400">Understand the Model Context Protocol</p>
                    </div>
                  </div>
                  
                  <div onClick={() => handleItemClick("installation")} className="border border-[#2A2D36] bg-transparent rounded-lg p-5 hover:border-blue-500 hover:shadow-lg cursor-pointer transition-all">
                    <div className="flex flex-col items-center text-center">
                      <Package className="h-8 w-8 text-blue-400 mb-3" />
                      <h3 className="font-medium text-base text-white mb-2">Installation</h3>
                      <p className="text-sm text-gray-400">Set up FluidAI MCP on your system</p>
                    </div>
                  </div>
                  
                  <div onClick={() => handleItemClick("getting-started")} className="border border-[#2A2D36] bg-transparent rounded-lg p-5 hover:border-blue-500 hover:shadow-lg cursor-pointer transition-all">
                    <div className="flex flex-col items-center text-center">
                      <Rocket className="h-8 w-8 text-blue-400 mb-3" />
                      <h3 className="font-medium text-base text-white mb-2">Getting Started</h3>
                      <p className="text-sm text-gray-400">Quick start guide for new users</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
         
          {/* What is MCP */}
          {activeItem === "what-is-mcp" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">Concepts</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">What is the Model Context Protocol (MCP)?</h1>
              
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  The Model Context Protocol (MCP) is a standardized framework that allows AI applications to connect with various tools and data sources. Think of it as a universal connector that enables seamless communication between AI models and external services.
                </p>
              </div>
             
              <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                <h3 className="text-2xl font-medium mb-5 text-white">Key Concepts</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="flex items-start gap-4 p-4 rounded-lg border border-[#2A2D36]" style={{ backgroundColor: 'hsl(240, 10%, 3.9%)' }}>
                    <Server className="h-6 w-6 text-blue-400 shrink-0 mt-1" />
                    <div>
                      <h4 className="font-semibold text-base text-white mb-2">MCP Servers</h4>
                      <p className="text-sm text-gray-400 leading-relaxed">
                        Services that implement the MCP specification and provide tools for AI models
                      </p>
                    </div>
                  </div>
                  
                  <div className="flex items-start gap-4 p-4 rounded-lg border border-[#2A2D36]" style={{ backgroundColor: 'hsl(240, 10%, 3.9%)' }}>
                    <Code className="h-6 w-6 text-blue-400 shrink-0 mt-1" />
                    <div>
                      <h4 className="font-semibold text-base text-white mb-2">Tools</h4>
                      <p className="text-sm text-gray-400 leading-relaxed">
                        Functions exposed by MCP servers that AI models can invoke to perform tasks
                      </p>
                    </div>
                  </div>
                  
                  <div className="flex items-start gap-4 p-4 rounded-lg border border-[#2A2D36]" style={{ backgroundColor: 'hsl(240, 10%, 3.9%)' }}>
                    <Package className="h-6 w-6 text-blue-400 shrink-0 mt-1" />
                    <div>
                      <h4 className="font-semibold text-base text-white mb-2">MCP Packages</h4>
                      <p className="text-sm text-gray-400 leading-relaxed">
                        Installable units containing MCP servers and their dependencies
                      </p>
                    </div>
                  </div>
                  
                  <div className="flex items-start gap-4 p-4 rounded-lg border border-[#2A2D36]" style={{ backgroundColor: 'hsl(240, 10%, 3.9%)' }}>
                    <BookOpen className="h-6 w-6 text-blue-400 shrink-0 mt-1" />
                    <div>
                      <h4 className="font-semibold text-base text-white mb-2">MCP Registry</h4>
                      <p className="text-sm text-gray-400 leading-relaxed">
                        A central repository where MCP packages can be published and discovered
                      </p>
                    </div>
                  </div>
                </div>
              </div>
              
              <div className="border border-[#2A2D36] rounded-lg p-6 bg-blue-500/5">
                <h3 className="text-2xl font-medium mb-5 text-white">Why Use MCP?</h3>
                <ul className="space-y-4">
                  <li className="flex items-start gap-3">
                    <div className="h-6 w-6 flex items-center justify-center rounded-full bg-blue-500/20 text-blue-400 mt-0.5 flex-shrink-0">✓</div>
                    <span className="text-gray-200 text-base">Standardized communication between AI models and external tools</span>
                  </li>
                  <li className="flex items-start gap-3">
                    <div className="h-6 w-6 flex items-center justify-center rounded-full bg-blue-500/20 text-blue-400 mt-0.5 flex-shrink-0">✓</div>
                    <span className="text-gray-200 text-base">Modular architecture allowing for easy extensibility</span>
                  </li>
                  <li className="flex items-start gap-3">
                    <div className="h-6 w-6 flex items-center justify-center rounded-full bg-blue-500/20 text-blue-400 mt-0.5 flex-shrink-0">✓</div>
                    <span className="text-gray-200 text-base">Simple installation and management of AI tools</span>
                  </li>
                </ul>
              </div>
            </div>
          )}
         
          {/* Getting Started */}
          {activeItem === "getting-started" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">Tutorials</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Getting Started</h1>
              
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  This guide will help you get started with the FluidAI MCP Installer, from installation to using your first MCP server.
                </p>
              </div>
             
              <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                <h3 className="text-2xl font-medium mb-6 text-white">Quick Start Guide</h3>
                <ol className="space-y-6 relative border-l border-gray-600 pl-8 ml-4">
                  <li className="relative">
                    <div className="absolute left-0 top-0 -translate-x-[1.5rem] rounded-full bg-blue-500 text-white flex items-center justify-center h-7 w-7 text-sm font-medium border-4 border-[#1A1D26]">1</div>
                    <h4 className="font-medium text-base text-white mb-2">Install FluidMCP</h4>
                    <p className="text-sm text-gray-400 mb-3">Install the package in development mode:</p>
                    <CodeBlock>pip install -e . && pip install -r requirements.txt</CodeBlock>
                  </li>
                  
                  <li className="relative">
                    <div className="absolute left-0 top-0 -translate-x-[1.5rem] rounded-full bg-blue-500 text-white flex items-center justify-center h-7 w-7 text-sm font-medium border-4 border-[#1A1D26]">2</div>
                    <h4 className="font-medium text-base text-white mb-2">Build the frontend</h4>
                    <p className="text-sm text-gray-400 mb-3">Navigate to the frontend directory and build:</p>
                    <CodeBlock>cd fluidmcp/frontend && npm install && npm run build && cd ../..</CodeBlock>
                  </li>
                  
                  <li className="relative">
                    <div className="absolute left-0 top-0 -translate-x-[1.5rem] rounded-full bg-blue-500 text-white flex items-center justify-center h-7 w-7 text-sm font-medium border-4 border-[#1A1D26]">3</div>
                    <h4 className="font-medium text-base text-white mb-2">Start the server</h4>
                    <p className="text-sm text-gray-400 mb-3">Run the FluidMCP server:</p>
                    <CodeBlock>fluidmcp serve --allow-insecure --allow-all-origins --port 8100</CodeBlock>
                  </li>
                </ol>
              </div>
              
              <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-5 flex items-start gap-4">
                <div className="text-blue-400 mt-1">
                  <Rocket className="h-6 w-6" />
                </div>
                <div>
                  <h3 className="font-medium text-base text-white mb-2">Next Steps</h3>
                  <p className="text-sm text-gray-300 leading-relaxed">
                    Once you have your server running, explore the API endpoints and start integrating MCP tools into your AI applications. Check the <span className="text-blue-400 cursor-pointer hover:underline" onClick={() => handleItemClick("api-access-fastapi")}>API documentation</span> for more details.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Prerequisites */}
          {activeItem === "prerequisites" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">Setup</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Prerequisites</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  Before installing FluidMCP, ensure your system meets the following requirements.
                </p>
              </div>

              <div className="space-y-6">
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white flex items-center gap-2">
                    <CheckCircle className="h-6 w-6 text-blue-400" />
                    System Requirements
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <h4 className="font-semibold text-base text-white mb-3">Python Environment</h4>
                      <ul className="space-y-2 text-sm text-gray-300">
                        <li className="flex items-start gap-2">
                          <span className="text-blue-400 mt-1">•</span>
                          <span>Python 3.8 or higher</span>
                        </li>
                        <li className="flex items-start gap-2">
                          <span className="text-blue-400 mt-1">•</span>
                          <span>pip package manager</span>
                        </li>
                        <li className="flex items-start gap-2">
                          <span className="text-blue-400 mt-1">•</span>
                          <span>Virtual environment (recommended)</span>
                        </li>
                      </ul>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <h4 className="font-semibold text-base text-white mb-3">Node.js (Optional)</h4>
                      <ul className="space-y-2 text-sm text-gray-300">
                        <li className="flex items-start gap-2">
                          <span className="text-blue-400 mt-1">•</span>
                          <span>Node.js 16+ for npm-based MCP servers</span>
                        </li>
                        <li className="flex items-start gap-2">
                          <span className="text-blue-400 mt-1">•</span>
                          <span>npm or npx command available</span>
                        </li>
                      </ul>
                    </div>
                  </div>
                </div>

                <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-5">
                  <h3 className="text-lg font-medium mb-3 text-white flex items-center gap-2">
                    <AlertCircle className="h-5 w-5 text-blue-400" />
                    Optional Components
                  </h3>
                  <ul className="space-y-3 text-sm text-gray-300">
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <div>
                        <strong className="text-white">AWS S3:</strong> For S3-based configuration management (master mode)
                      </div>
                    </li>
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <div>
                        <strong className="text-white">Docker:</strong> For containerized deployments
                      </div>
                    </li>
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <div>
                        <strong className="text-white">Git:</strong> For installing packages from Git repositories
                      </div>
                    </li>
                  </ul>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-xl font-medium mb-4 text-white">Verify Your Installation</h3>
                  <p className="text-sm text-gray-300 mb-3">Check Python version:</p>
                  <CodeBlock>python --version</CodeBlock>
                  <p className="text-sm text-gray-300 mb-3 mt-4">Check pip version:</p>
                  <CodeBlock>pip --version</CodeBlock>
                  <p className="text-sm text-gray-300 mb-3 mt-4">Check Node.js (optional):</p>
                  <CodeBlock>node --version</CodeBlock>
                </div>
              </div>
            </div>
          )}

          {/* Installation */}
          {activeItem === "installation" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">Setup</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Installation</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  Install FluidMCP CLI and start managing your MCP servers.
                </p>
              </div>

              <div className="space-y-6">
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Standard Installation</h3>
                  <p className="text-sm text-gray-300 mb-4">Install FluidMCP using pip:</p>
                  <CodeBlock>pip install fluidmcp</CodeBlock>
                  
                  <div className="mt-6 pt-6 border-t border-[#2A2D36]">
                    <h4 className="font-semibold text-base text-white mb-3">Verify Installation</h4>
                    <p className="text-sm text-gray-300 mb-3">Check the installed version:</p>
                    <CodeBlock>fluidmcp --version</CodeBlock>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Development Installation</h3>
                  <p className="text-sm text-gray-300 mb-4">For development or contributing to FluidMCP:</p>
                  <CodeBlock language="bash">{`# Clone the repository
git clone https://github.com/Fluid-AI/fluidmcp.git
cd fluidmcp

# Install in editable mode with development dependencies
pip install -e .`}</CodeBlock>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Docker Installation</h3>
                  <p className="text-sm text-gray-300 mb-4">Run FluidMCP in a container:</p>
                  <CodeBlock language="bash">{`# Build the Docker image
docker build -t fluidmcp .

# Run FluidMCP server
docker run -p 8099:8099 fluidmcp`}</CodeBlock>
                </div>

                <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-5 flex items-start gap-4">
                  <Rocket className="h-6 w-6 text-blue-400 mt-1 flex-shrink-0" />
                  <div>
                    <h3 className="font-medium text-base text-white mb-2">Next Steps</h3>
                    <p className="text-sm text-gray-300 leading-relaxed">
                      After installation, you can start installing MCP servers. Check the{" "}
                      <span className="text-blue-400 cursor-pointer hover:underline" onClick={() => handleItemClick("installing-server")}>
                        Installing an MCP Server
                      </span>{" "}
                      guide to continue.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Installing an MCP Server */}
          {activeItem === "installing-server" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">Usage</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Installing an MCP Server</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  Step-by-step guide to installing MCP servers from various sources.
                </p>
              </div>

              <div className="space-y-6">
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Basic Installation</h3>
                  <p className="text-sm text-gray-300 mb-4">Install an MCP package using the standard format:</p>
                  <CodeBlock>fluidmcp install author/package@version</CodeBlock>
                  
                  <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                    <h4 className="font-semibold text-base text-white mb-3">Examples</h4>
                    <div className="space-y-3">
                      <div>
                        <p className="text-sm text-gray-400 mb-2">Install specific version:</p>
                        <CodeBlock>fluidmcp install modelcontextprotocol/server-filesystem@1.0.0</CodeBlock>
                      </div>
                      <div className="mt-4">
                        <p className="text-sm text-gray-400 mb-2">Install latest version (omit version):</p>
                        <CodeBlock>fluidmcp install modelcontextprotocol/server-filesystem</CodeBlock>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Installation Sources</h3>
                  <div className="space-y-4">
                    <div className="border border-[#2A2D36] rounded-lg p-5">
                      <div className="flex items-start gap-3 mb-3">
                        <Package className="h-6 w-6 text-blue-400 flex-shrink-0 mt-1" />
                        <div>
                          <h4 className="font-semibold text-base text-white mb-2">From MCP Registry</h4>
                          <p className="text-sm text-gray-300 mb-3">Install from the official FluidMCP registry:</p>
                          <CodeBlock language="bash">{`# Configure registry access
export MCP_FETCH_URL="https://registry.fluidmcp.com/fetch-mcp-package"
export MCP_TOKEN="your-registry-token"

# Install package
fluidmcp install author/package@version`}</CodeBlock>
                        </div>
                      </div>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5">
                      <div className="flex items-start gap-3 mb-3">
                        <Server className="h-6 w-6 text-blue-400 flex-shrink-0 mt-1" />
                        <div>
                          <h4 className="font-semibold text-base text-white mb-2">From NPM Packages</h4>
                          <p className="text-sm text-gray-300 mb-3">Many MCP servers are available as npm packages:</p>
                          <CodeBlock language="bash">{`# Install npm-based server
# Configure in config.json with npx command
{
  "mcpServers": {
    "my-server": {
      "command": "npx",
      "args": ["-y", "@author/package-name"]
    }
  }
}`}</CodeBlock>
                        </div>
                      </div>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5">
                      <div className="flex items-start gap-3 mb-3">
                        <Code className="h-6 w-6 text-blue-400 flex-shrink-0 mt-1" />
                        <div>
                          <h4 className="font-semibold text-base text-white mb-2">Python-based Servers</h4>
                          <p className="text-sm text-gray-300 mb-3">Install Python MCP servers:</p>
                          <CodeBlock language="bash">{`# Configure Python server in config.json
{
  "mcpServers": {
    "python-server": {
      "command": "python",
      "args": ["-m", "your_mcp_package"],
      "env": {
        "API_KEY": "your-key"
      }
    }
  }
}`}</CodeBlock>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Managing Environment Variables</h3>
                  <p className="text-sm text-gray-300 mb-4">Edit environment variables for an installed package:</p>
                  <CodeBlock>fluidmcp edit-env author/package@version</CodeBlock>
                  <p className="text-sm text-gray-400 mt-4">This opens an interactive editor to configure environment variables securely.</p>
                </div>

                <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-5 flex items-start gap-4">
                  <Zap className="h-6 w-6 text-blue-400 mt-1 flex-shrink-0" />
                  <div>
                    <h3 className="font-medium text-base text-white mb-2">Validation</h3>
                    <p className="text-sm text-gray-300 mb-3">
                      Validate your installation and configuration:
                    </p>
                    <CodeBlock>fluidmcp validate author/package@version</CodeBlock>
                    <p className="text-sm text-gray-400 mt-3">
                      This checks command availability, environment variables, and configuration structure.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Running an Installed Package */}
          {activeItem === "running-installed" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">Usage</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Running an Installed Package</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  Launch and manage your MCP servers with the FluidMCP FastAPI gateway.
                </p>
              </div>

              <div className="space-y-6">
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Running a Single Server</h3>
                  <p className="text-sm text-gray-300 mb-4">Start an installed MCP server:</p>
                  <CodeBlock>fluidmcp run author/package@version --start-server</CodeBlock>
                  
                  <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                    <p className="text-sm text-gray-300 mb-3">The server will be available at:</p>
                    <CodeBlock>http://localhost:8099</CodeBlock>
                    <p className="text-sm text-gray-400 mt-3">API documentation: <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">http://localhost:8099/docs</code></p>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Running Multiple Servers</h3>
                  
                  <div className="space-y-4">
                    <div>
                      <h4 className="font-semibold text-base text-white mb-3">From Configuration File</h4>
                      <p className="text-sm text-gray-300 mb-3">Run all servers from a config.json:</p>
                      <CodeBlock>fluidmcp run config.json --file --start-server</CodeBlock>
                    </div>

                    <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                      <h4 className="font-semibold text-base text-white mb-3">Run All Installed</h4>
                      <p className="text-sm text-gray-300 mb-3">Run all locally installed packages:</p>
                      <CodeBlock>fluidmcp run all --start-server</CodeBlock>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Secure Mode</h3>
                  <p className="text-sm text-gray-300 mb-4">Enable bearer token authentication for production:</p>
                  <CodeBlock language="bash">{`# With auto-generated token
fluidmcp run config.json --file --secure --start-server

# With custom token
fluidmcp run config.json --file --secure --token "your-secret-token" --start-server`}</CodeBlock>
                  
                  <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                    <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-4 flex items-start gap-3">
                      <AlertCircle className="h-5 w-5 text-yellow-400 mt-0.5 flex-shrink-0" />
                      <div>
                        <h4 className="font-semibold text-sm text-white mb-2">Security Note</h4>
                        <p className="text-sm text-gray-300">
                          The token is saved to <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">~/.fmcp/tokens/current_token.txt</code> with 
                          restricted permissions (600). All API requests require this token in the Authorization header.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Custom Port Configuration</h3>
                  <p className="text-sm text-gray-300 mb-4">By default, FluidMCP runs on port 8099. The port can be configured via environment variable or programmatically.</p>
                  <CodeBlock language="bash">{`# Set custom port via environment
export FMCP_PORT=8080
fluidmcp run config.json --file --start-server`}</CodeBlock>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Server Status and Logs</h3>
                  <p className="text-sm text-gray-300 mb-4">The gateway provides real-time server status and logging:</p>
                  <ul className="space-y-3 text-sm text-gray-300">
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <span>Access logs at <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">/api/servers/{"{id}"}/logs</code></span>
                    </li>
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <span>Check status at <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">/api/servers/{"{id}"}/status</code></span>
                    </li>
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <span>View all servers at <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">/api/servers</code></span>
                    </li>
                  </ul>
                </div>

                <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-5 flex items-start gap-4">
                  <Server className="h-6 w-6 text-blue-400 mt-1 flex-shrink-0" />
                  <div>
                    <h3 className="font-medium text-base text-white mb-2">Frontend Dashboard</h3>
                    <p className="text-sm text-gray-300">
                      Access the interactive dashboard at <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">http://localhost:8099</code> to 
                      monitor servers, view logs, and manage configurations through a modern web interface.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Listing Packages */}
          {activeItem === "listing-packages" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">Usage</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Listing Installed Packages</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  View and manage your installed MCP packages.
                </p>
              </div>

              <div className="space-y-6">
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">List All Installed Packages</h3>
                  <p className="text-sm text-gray-300 mb-4">Display all installed MCP packages:</p>
                  <CodeBlock>fluidmcp list</CodeBlock>
                  
                  <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                    <h4 className="font-semibold text-base text-white mb-3">Output Information</h4>
                    <p className="text-sm text-gray-300 mb-3">The list command displays:</p>
                    <ul className="space-y-2 text-sm text-gray-300">
                      <li className="flex items-start gap-2">
                        <span className="text-blue-400 mt-1">•</span>
                        <span>Package author and name</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="text-blue-400 mt-1">•</span>
                        <span>Installed version(s)</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="text-blue-400 mt-1">•</span>
                        <span>Installation path</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="text-blue-400 mt-1">•</span>
                        <span>Package metadata</span>
                      </li>
                    </ul>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Installation Directory</h3>
                  <p className="text-sm text-gray-300 mb-3">Packages are installed to:</p>
                  <CodeBlock>{`~/.fluidmcp/packages/{author}/{package}/{version}/`}</CodeBlock>
                  <p className="text-sm text-gray-400 mt-4">Each package includes a metadata.json file with configuration details.</p>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Via API</h3>
                  <p className="text-sm text-gray-300 mb-4">List servers via the management API:</p>
                  <CodeBlock language="bash">{`# Get all servers
curl http://localhost:8099/api/servers

# With authentication (secure mode)
curl -H "Authorization: Bearer your-token" \\
  http://localhost:8099/api/servers`}</CodeBlock>
                </div>
              </div>
            </div>
          )}

          {/* Alternative Commands */}
          {activeItem === "alternative-commands" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">Usage</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Alternative Commands</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  Additional FluidMCP commands for advanced usage and management.
                </p>
              </div>

              <div className="space-y-6">
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Configuration Validation</h3>
                  <p className="text-sm text-gray-300 mb-4">Validate configuration files and installed packages:</p>
                  <CodeBlock language="bash">{`# Validate a configuration file
fluidmcp validate config.json --file

# Validate an installed package
fluidmcp validate author/package@version`}</CodeBlock>
                  
                  <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                    <h4 className="font-semibold text-base text-white mb-3">Validation Checks</h4>
                    <ul className="space-y-2 text-sm text-gray-300">
                      <li className="flex items-start gap-2">
                        <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                        <span>Configuration file structure and syntax</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                        <span>Command availability in system PATH</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                        <span>Required environment variables</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                        <span>Metadata file existence</span>
                      </li>
                    </ul>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Environment Management</h3>
                  <p className="text-sm text-gray-300 mb-4">Edit environment variables for packages:</p>
                  <CodeBlock>fluidmcp edit-env author/package@version</CodeBlock>
                  <p className="text-sm text-gray-400 mt-4">
                    Opens an interactive editor for secure environment configuration. 
                    Variables are stored encrypted and loaded at runtime.
                  </p>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Version Information</h3>
                  <p className="text-sm text-gray-300 mb-4">Display FluidMCP version and system info:</p>
                  <CodeBlock>fluidmcp --version</CodeBlock>
                  
                  <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                    <h4 className="font-semibold text-base text-white mb-3">Displays</h4>
                    <ul className="space-y-2 text-sm text-gray-300">
                      <li className="flex items-start gap-2">
                        <span className="text-blue-400 mt-1">•</span>
                        <span>FluidMCP version</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="text-blue-400 mt-1">•</span>
                        <span>Python version</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="text-blue-400 mt-1">•</span>
                        <span>Operating system</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="text-blue-400 mt-1">•</span>
                        <span>Installation path</span>
                      </li>
                    </ul>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Verbose Logging</h3>
                  <p className="text-sm text-gray-300 mb-4">Enable detailed debug logging:</p>
                  <CodeBlock language="bash">{`# With any command
fluidmcp run config.json --file --start-server --verbose

# For debugging installation issues
fluidmcp install author/package@version --verbose`}</CodeBlock>
                  <p className="text-sm text-gray-400 mt-4">Verbose mode sets logging to DEBUG level for troubleshooting.</p>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">S3 Operations</h3>
                  <p className="text-sm text-gray-300 mb-4">Work with S3-based configurations:</p>
                  <CodeBlock language="bash">{`# Run from S3 URL
fluidmcp run "https://bucket.s3.amazonaws.com/config.json" --s3 --start-server

# Install in master mode (S3-driven)
fluidmcp install author/package@version --master

# Run all packages with S3 coordination
fluidmcp run all --master --start-server`}</CodeBlock>
                </div>
              </div>
            </div>
          )}

          {/* API Access via FastAPI */}
          {activeItem === "api-access-fastapi" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">API</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">API Access via FastAPI</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  FluidMCP provides a comprehensive REST API for managing MCP servers programmatically.
                </p>
              </div>

              <div className="space-y-6">
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">API Gateway Overview</h3>
                  <p className="text-sm text-gray-300 mb-4">
                    The FluidMCP gateway runs on port <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">8099</code> by default and provides:
                  </p>
                  <ul className="space-y-3 text-sm text-gray-300">
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <span><strong className="text-white">Management API:</strong> Full CRUD operations for server configurations</span>
                    </li>
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <span><strong className="text-white">Dynamic MCP Router:</strong> Forward MCP requests to specific servers</span>
                    </li>
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <span><strong className="text-white">Health & Metrics:</strong> Monitoring endpoints for production deployment</span>
                    </li>
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <span><strong className="text-white">Frontend UI:</strong> Interactive dashboard served from the same port</span>
                    </li>
                  </ul>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Starting the API Server</h3>
                  <p className="text-sm text-gray-300 mb-4">Start the server with any run command:</p>
                  <CodeBlock language="bash">{`# Start with configuration file
fluidmcp run config.json --file --start-server

# Start with a single package
fluidmcp run author/package@version --start-server

# Start all installed packages
fluidmcp run all --start-server`}</CodeBlock>
                  
                  <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                    <h4 className="font-semibold text-base text-white mb-3">Server URLs</h4>
                    <div className="space-y-2 text-sm text-gray-300">
                      <div className="flex items-start gap-3">
                        <span className="text-blue-400">•</span>
                        <span><strong className="text-white">API Documentation:</strong> <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">http://localhost:8099/docs</code></span>
                      </div>
                      <div className="flex items-start gap-3">
                        <span className="text-blue-400">•</span>
                        <span><strong className="text-white">Dashboard:</strong> <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">http://localhost:8099</code></span>
                      </div>
                      <div className="flex items-start gap-3">
                        <span className="text-blue-400">•</span>
                        <span><strong className="text-white">Health Check:</strong> <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">http://localhost:8099/health</code></span>
                      </div>
                      <div className="flex items-start gap-3">
                        <span className="text-blue-400">•</span>
                        <span><strong className="text-white">Metrics:</strong> <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">http://localhost:8099/metrics</code></span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Authentication</h3>
                  
                  <div className="space-y-4">
                    <div>
                      <h4 className="font-semibold text-base text-white mb-3">Development Mode (Default)</h4>
                      <p className="text-sm text-gray-300 mb-3">No authentication required - suitable for local development:</p>
                      <CodeBlock language="bash">fluidmcp run config.json --file --start-server</CodeBlock>
                    </div>

                    <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                      <h4 className="font-semibold text-base text-white mb-3">Secure Mode (Production)</h4>
                      <p className="text-sm text-gray-300 mb-3">Enable bearer token authentication:</p>
                      <CodeBlock language="bash">{`# Auto-generate token
fluidmcp run config.json --file --secure --start-server

# Use custom token
fluidmcp run config.json --file --secure --token "your-secret-token" --start-server`}</CodeBlock>
                      
                      <div className="mt-4 bg-blue-500/5 border border-blue-500/20 rounded-lg p-4">
                        <p className="text-sm text-gray-300 mb-2">
                          The token is saved to <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">~/.fmcp/tokens/current_token.txt</code> with 
                          permissions <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">600</code>.
                        </p>
                        <p className="text-sm text-gray-300 mb-3">
                          Include the token in all API requests:
                        </p>
                        <CodeBlock language="bash">{`curl -H "Authorization: Bearer YOUR_TOKEN" \\
  http://localhost:8099/api/servers`}</CodeBlock>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">CORS Configuration</h3>
                  <p className="text-sm text-gray-300 mb-4">
                    FluidMCP uses secure CORS defaults (localhost only). For production deployments with custom origins:
                  </p>
                  <CodeBlock language="python">{`# In your code
from fluidmcp.cli.server import create_app

app = await create_app(
    db_manager=db_manager,
    server_manager=server_manager,
    allowed_origins=[
        "https://yourdomain.com",
        "https://app.yourdomain.com"
    ]
)`}</CodeBlock>
                  
                  <div className="mt-4 bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-4 flex items-start gap-3">
                    <AlertCircle className="h-5 w-5 text-yellow-400 mt-0.5 flex-shrink-0" />
                    <div>
                      <h4 className="font-semibold text-sm text-white mb-2">Security Warning</h4>
                      <p className="text-sm text-gray-300">
                        Never use <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">["*"]</code> wildcards in production.
                        This allows any website to access your API.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Available API Endpoints */}
          {activeItem === "available-endpoints" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">API</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Available API Endpoints</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  Complete reference of all FluidMCP REST API endpoints.
                </p>
              </div>

              <div className="space-y-6">
                {/* Server Management Endpoints */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white flex items-center gap-2">
                    <Server className="h-6 w-6 text-blue-400" />
                    Server Management
                  </h3>
                  
                  <div className="space-y-4">
                    {/* POST /servers */}
                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <Badge className="bg-green-500/10 text-green-400 border-none text-xs">POST</Badge>
                        <code className="text-sm text-blue-400">/api/servers</code>
                      </div>
                      <p className="text-sm text-gray-300 mb-3">Add a new MCP server configuration</p>
                      <CodeBlock language="json">{`{
  "id": "my-server",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"],
  "env": {
    "API_KEY": "your-key"
  }
}`}</CodeBlock>
                    </div>

                    {/* GET /servers */}
                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <Badge className="bg-blue-500/10 text-blue-400 border-none text-xs">GET</Badge>
                        <code className="text-sm text-blue-400">/api/servers</code>
                      </div>
                      <p className="text-sm text-gray-300">List all configured servers</p>
                    </div>

                    {/* GET /servers/{id} */}
                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <Badge className="bg-blue-500/10 text-blue-400 border-none text-xs">GET</Badge>
                        <code className="text-sm text-blue-400">/api/servers/{"{id}"}</code>
                      </div>
                      <p className="text-sm text-gray-300">Get details of a specific server</p>
                    </div>

                    {/* PUT /servers/{id} */}
                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <Badge className="bg-yellow-500/10 text-yellow-400 border-none text-xs">PUT</Badge>
                        <code className="text-sm text-blue-400">/api/servers/{"{id}"}</code>
                      </div>
                      <p className="text-sm text-gray-300">Update server configuration</p>
                    </div>

                    {/* DELETE /servers/{id} */}
                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <Badge className="bg-red-500/10 text-red-400 border-none text-xs">DELETE</Badge>
                        <code className="text-sm text-blue-400">/api/servers/{"{id}"}</code>
                      </div>
                      <p className="text-sm text-gray-300">Remove a server configuration</p>
                    </div>
                  </div>
                </div>

                {/* Server Control Endpoints */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white flex items-center gap-2">
                    <Zap className="h-6 w-6 text-blue-400" />
                    Server Control
                  </h3>
                  
                  <div className="space-y-4">
                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <Badge className="bg-green-500/10 text-green-400 border-none text-xs">POST</Badge>
                        <code className="text-sm text-blue-400">/api/servers/{"{id}"}/start</code>
                      </div>
                      <p className="text-sm text-gray-300">Start a server</p>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <Badge className="bg-green-500/10 text-green-400 border-none text-xs">POST</Badge>
                        <code className="text-sm text-blue-400">/api/servers/{"{id}"}/stop</code>
                      </div>
                      <p className="text-sm text-gray-300">Stop a running server</p>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <Badge className="bg-green-500/10 text-green-400 border-none text-xs">POST</Badge>
                        <code className="text-sm text-blue-400">/api/servers/{"{id}"}/restart</code>
                      </div>
                      <p className="text-sm text-gray-300">Restart a server</p>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <Badge className="bg-green-500/10 text-green-400 border-none text-xs">POST</Badge>
                        <code className="text-sm text-blue-400">/api/servers/start-all</code>
                      </div>
                      <p className="text-sm text-gray-300">Start all configured servers</p>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <Badge className="bg-green-500/10 text-green-400 border-none text-xs">POST</Badge>
                        <code className="text-sm text-blue-400">/api/servers/stop-all</code>
                      </div>
                      <p className="text-sm text-gray-300">Stop all running servers</p>
                    </div>
                  </div>
                </div>

                {/* Monitoring Endpoints */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white flex items-center gap-2">
                    <AlertCircle className="h-6 w-6 text-blue-400" />
                    Monitoring & Logs
                  </h3>
                  
                  <div className="space-y-4">
                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <Badge className="bg-blue-500/10 text-blue-400 border-none text-xs">GET</Badge>
                        <code className="text-sm text-blue-400">/api/servers/{"{id}"}/status</code>
                      </div>
                      <p className="text-sm text-gray-300 mb-3">Get server status (running, stopped, error)</p>
                      <CodeBlock language="json">{`{
  "status": "running",
  "uptime": 3600.5,
  "pid": 12345
}`}</CodeBlock>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <Badge className="bg-blue-500/10 text-blue-400 border-none text-xs">GET</Badge>
                        <code className="text-sm text-blue-400">/api/servers/{"{id}"}/logs</code>
                      </div>
                      <p className="text-sm text-gray-300">Retrieve server logs (stdout/stderr)</p>
                      <p className="text-sm text-gray-400 mt-2">Query params: <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">lines=100</code></p>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <Badge className="bg-blue-500/10 text-blue-400 border-none text-xs">GET</Badge>
                        <code className="text-sm text-blue-400">/health</code>
                      </div>
                      <p className="text-sm text-gray-300">Health check with database status</p>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <Badge className="bg-blue-500/10 text-blue-400 border-none text-xs">GET</Badge>
                        <code className="text-sm text-blue-400">/metrics</code>
                      </div>
                      <p className="text-sm text-gray-300">Prometheus-compatible metrics endpoint</p>
                    </div>
                  </div>
                </div>

                {/* Environment Variables */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white flex items-center gap-2">
                    <Key className="h-6 w-6 text-blue-400" />
                    Environment Variables
                  </h3>
                  
                  <div className="space-y-4">
                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <Badge className="bg-blue-500/10 text-blue-400 border-none text-xs">GET</Badge>
                        <code className="text-sm text-blue-400">/api/servers/{"{id}"}/instance/env</code>
                      </div>
                      <p className="text-sm text-gray-300">Get environment variables (masked values)</p>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <Badge className="bg-yellow-500/10 text-yellow-400 border-none text-xs">PUT</Badge>
                        <code className="text-sm text-blue-400">/api/servers/{"{id}"}/instance/env</code>
                      </div>
                      <p className="text-sm text-gray-300 mb-3">Update environment variables</p>
                      <CodeBlock language="json">{`{
  "API_KEY": "new-value",
  "DEBUG": "true"
}`}</CodeBlock>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <Badge className="bg-red-500/10 text-red-400 border-none text-xs">DELETE</Badge>
                        <code className="text-sm text-blue-400">/api/servers/{"{id}"}/instance/env</code>
                      </div>
                      <p className="text-sm text-gray-300">Delete specific environment variables</p>
                      <p className="text-sm text-gray-400 mt-2">Body: <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">{`{"keys": ["API_KEY"]}`}</code></p>
                    </div>
                  </div>
                </div>

                {/* Tool Execution */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white flex items-center gap-2">
                    <Wrench className="h-6 w-6 text-blue-400" />
                    Tool Execution
                  </h3>
                  
                  <div className="space-y-4">
                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <Badge className="bg-blue-500/10 text-blue-400 border-none text-xs">GET</Badge>
                        <code className="text-sm text-blue-400">/api/servers/{"{id}"}/tools</code>
                      </div>
                      <p className="text-sm text-gray-300">List available tools from a server</p>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <Badge className="bg-green-500/10 text-green-400 border-none text-xs">POST</Badge>
                        <code className="text-sm text-blue-400">/api/servers/{"{id}"}/tools/{"{tool_name}"}/run</code>
                      </div>
                      <p className="text-sm text-gray-300 mb-3">Execute a specific tool</p>
                      <CodeBlock language="json">{`{
  "arguments": {
    "param1": "value1",
    "param2": "value2"
  }
}`}</CodeBlock>
                    </div>
                  </div>
                </div>

                {/* LLM Management (vLLM) */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white flex items-center gap-2">
                    <Zap className="h-6 w-6 text-blue-400" />
                    LLM Management (vLLM)
                  </h3>
                  
                  <div className="space-y-4">
                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <Badge className="bg-blue-500/10 text-blue-400 border-none text-xs">GET</Badge>
                        <code className="text-sm text-blue-400">/api/llm/models</code>
                      </div>
                      <p className="text-sm text-gray-300">List all LLM models</p>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <Badge className="bg-blue-500/10 text-blue-400 border-none text-xs">GET</Badge>
                        <code className="text-sm text-blue-400">/api/llm/models/{"{model_id}"}</code>
                      </div>
                      <p className="text-sm text-gray-300">Get LLM model details</p>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <Badge className="bg-green-500/10 text-green-400 border-none text-xs">POST</Badge>
                        <code className="text-sm text-blue-400">/api/llm/models/{"{model_id}"}/restart</code>
                      </div>
                      <p className="text-sm text-gray-300">Restart an LLM model</p>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <Badge className="bg-green-500/10 text-green-400 border-none text-xs">POST</Badge>
                        <code className="text-sm text-blue-400">/api/llm/models/{"{model_id}"}/stop</code>
                      </div>
                      <p className="text-sm text-gray-300">Stop an LLM model</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Example API Call */}
          {activeItem === "example-call" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">API</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Example API Call</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  Practical examples of using the FluidMCP API.
                </p>
              </div>

              <div className="space-y-6">
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Adding a Server</h3>
                  <p className="text-sm text-gray-300 mb-4">Create a new MCP server configuration:</p>
                  <CodeBlock language="bash">{`curl -X POST http://localhost:8099/api/servers \\
  -H "Content-Type: application/json" \\
  -d '{
    "id": "filesystem",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    "env": {}
  }'`}</CodeBlock>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Starting a Server</h3>
                  <p className="text-sm text-gray-300 mb-4">Start the configured server:</p>
                  <CodeBlock language="bash">{`curl -X POST http://localhost:8099/api/servers/filesystem/start`}</CodeBlock>
                  
                  <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                    <h4 className="font-semibold text-base text-white mb-3">Response</h4>
                    <CodeBlock language="json">{`{
  "message": "Server filesystem started successfully",
  "server_id": "filesystem",
  "pid": 12345,
  "status": "running"
}`}</CodeBlock>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Checking Server Status</h3>
                  <p className="text-sm text-gray-300 mb-4">Get real-time server status:</p>
                  <CodeBlock language="bash">{`curl http://localhost:8099/api/servers/filesystem/status`}</CodeBlock>
                  
                  <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                    <h4 className="font-semibold text-base text-white mb-3">Response</h4>
                    <CodeBlock language="json">{`{
  "id": "filesystem",
  "status": "running",
  "pid": 12345,
  "uptime": 3600.5,
  "last_started": "2026-02-05T10:30:00Z"
}`}</CodeBlock>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Listing Available Tools</h3>
                  <p className="text-sm text-gray-300 mb-4">Query tools from a running server:</p>
                  <CodeBlock language="bash">{`curl http://localhost:8099/api/servers/filesystem/tools`}</CodeBlock>
                  
                  <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                    <h4 className="font-semibold text-base text-white mb-3">Response</h4>
                    <CodeBlock language="json">{`{
  "tools": [
    {
      "name": "read_file",
      "description": "Read contents of a file",
      "inputSchema": {
        "type": "object",
        "properties": {
          "path": {"type": "string"}
        },
        "required": ["path"]
      }
    },
    {
      "name": "write_file",
      "description": "Write contents to a file",
      "inputSchema": {
        "type": "object",
        "properties": {
          "path": {"type": "string"},
          "content": {"type": "string"}
        },
        "required": ["path", "content"]
      }
    }
  ]
}`}</CodeBlock>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Executing a Tool</h3>
                  <p className="text-sm text-gray-300 mb-4">Call a tool with arguments:</p>
                  <CodeBlock language="bash">{`curl -X POST http://localhost:8099/api/servers/filesystem/tools/read_file/run \\
  -H "Content-Type: application/json" \\
  -d '{
    "arguments": {
      "path": "/tmp/example.txt"
    }
  }'`}</CodeBlock>
                  
                  <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                    <h4 className="font-semibold text-base text-white mb-3">Response</h4>
                    <CodeBlock language="json">{`{
  "content": [
    {
      "type": "text",
      "text": "File contents here..."
    }
  ]
}`}</CodeBlock>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">With Authentication (Secure Mode)</h3>
                  <p className="text-sm text-gray-300 mb-4">Include bearer token in requests:</p>
                  <CodeBlock language="bash">{`# Set token from file
TOKEN=$(cat ~/.fmcp/tokens/current_token.txt)

# Make authenticated request
curl -H "Authorization: Bearer $TOKEN" \\
  http://localhost:8099/api/servers`}</CodeBlock>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Python Example</h3>
                  <p className="text-sm text-gray-300 mb-4">Using requests library:</p>
                  <CodeBlock language="python">{`import requests

BASE_URL = "http://localhost:8099"

# Add server
response = requests.post(
    f"{BASE_URL}/api/servers",
    json={
        "id": "my-server",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        "env": {}
    }
)
print(response.json())

# Start server
response = requests.post(f"{BASE_URL}/api/servers/my-server/start")
print(response.json())

# Get tools
response = requests.get(f"{BASE_URL}/api/servers/my-server/tools")
tools = response.json()["tools"]
print(f"Available tools: {[t['name'] for t in tools]}")

# Execute tool
response = requests.post(
    f"{BASE_URL}/api/servers/my-server/tools/read_file/run",
    json={
        "arguments": {
            "path": "/tmp/example.txt"
        }
    }
)
print(response.json())`}</CodeBlock>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">JavaScript/TypeScript Example</h3>
                  <p className="text-sm text-gray-300 mb-4">Using fetch API:</p>
                  <CodeBlock language="typescript">{`const BASE_URL = "http://localhost:8099";

// Add server
const addResponse = await fetch(\`\${BASE_URL}/api/servers\`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    id: "my-server",
    command: "npx",
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    env: {}
  })
});
console.log(await addResponse.json());

// Start server
const startResponse = await fetch(
  \`\${BASE_URL}/api/servers/my-server/start\`,
  { method: "POST" }
);
console.log(await startResponse.json());

// Get tools
const toolsResponse = await fetch(
  \`\${BASE_URL}/api/servers/my-server/tools\`
);
const { tools } = await toolsResponse.json();
console.log("Available tools:", tools.map(t => t.name));

// Execute tool
const execResponse = await fetch(
  \`\${BASE_URL}/api/servers/my-server/tools/read_file/run\`,
  {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      arguments: { path: "/tmp/example.txt" }
    })
  }
);
console.log(await execResponse.json());`}</CodeBlock>
                </div>
              </div>
            </div>
          )}

          {/* Managing API Keys */}
          {activeItem === "managing-keys" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">API</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Managing API Keys</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  Securely manage environment variables and API keys for your MCP servers.
                </p>
              </div>

              <div className="space-y-6">
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Via CLI (Recommended)</h3>
                  <p className="text-sm text-gray-300 mb-4">Use the interactive editor to manage environment variables:</p>
                  <CodeBlock>fluidmcp edit-env author/package@version</CodeBlock>
                  
                  <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                    <p className="text-sm text-gray-300 mb-3">This opens an editor where you can set:</p>
                    <ul className="space-y-2 text-sm text-gray-300">
                      <li className="flex items-start gap-2">
                        <span className="text-blue-400 mt-1">•</span>
                        <span>API keys and secrets</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="text-blue-400 mt-1">•</span>
                        <span>Database credentials</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="text-blue-400 mt-1">•</span>
                        <span>Service URLs and endpoints</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="text-blue-400 mt-1">•</span>
                        <span>Any environment-specific configuration</span>
                      </li>
                    </ul>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Via Configuration File</h3>
                  <p className="text-sm text-gray-300 mb-4">Include environment variables in your config.json:</p>
                  <CodeBlock language="json">{`{
  "mcpServers": {
    "google-maps": {
      "command": "npx",
      "args": ["-y", "@google-maps/mcp-server"],
      "env": {
        "GOOGLE_MAPS_API_KEY": "your-api-key-here",
        "DEBUG": "false"
      }
    }
  }
}`}</CodeBlock>
                  
                  <div className="mt-4 bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-4 flex items-start gap-3">
                    <AlertCircle className="h-5 w-5 text-yellow-400 mt-0.5 flex-shrink-0" />
                    <div>
                      <h4 className="font-semibold text-sm text-white mb-2">Security Warning</h4>
                      <p className="text-sm text-gray-300">
                        Avoid committing API keys to version control. Use environment variable substitution or separate secure files.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Via API</h3>
                  
                  <div className="space-y-4">
                    <div>
                      <h4 className="font-semibold text-base text-white mb-3">Get Environment Variables</h4>
                      <p className="text-sm text-gray-300 mb-3">Values are masked for security:</p>
                      <CodeBlock language="bash">{`curl http://localhost:8099/api/servers/my-server/instance/env`}</CodeBlock>
                      
                      <div className="mt-3">
                        <p className="text-sm text-gray-400 mb-2">Response:</p>
                        <CodeBlock language="json">{`{
  "API_KEY": "***MASKED***",
  "DEBUG": "true"
}`}</CodeBlock>
                      </div>
                    </div>

                    <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                      <h4 className="font-semibold text-base text-white mb-3">Update Environment Variables</h4>
                      <CodeBlock language="bash">{`curl -X PUT http://localhost:8099/api/servers/my-server/instance/env \\
  -H "Content-Type: application/json" \\
  -d '{
    "API_KEY": "new-api-key",
    "NEW_VAR": "value"
  }'`}</CodeBlock>
                      <p className="text-sm text-gray-400 mt-3">Note: Requires server restart to take effect</p>
                    </div>

                    <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                      <h4 className="font-semibold text-base text-white mb-3">Delete Environment Variables</h4>
                      <CodeBlock language="bash">{`curl -X DELETE http://localhost:8099/api/servers/my-server/instance/env \\
  -H "Content-Type: application/json" \\
  -d '{
    "keys": ["OLD_VAR", "DEPRECATED_KEY"]
  }'`}</CodeBlock>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Environment Variable Substitution</h3>
                  <p className="text-sm text-gray-300 mb-4">Reference system environment variables in config:</p>
                  <CodeBlock language="json">{`{
  "mcpServers": {
    "google-maps": {
      "command": "npx",
      "args": ["-y", "@google-maps/mcp-server"],
      "env": {
        "GOOGLE_MAPS_API_KEY": "\${GOOGLE_MAPS_API_KEY}",
        "DEBUG": "\${DEBUG:-false}"
      }
    }
  }
}`}</CodeBlock>
                  
                  <div className="mt-4">
                    <p className="text-sm text-gray-300 mb-3">Then set in your shell:</p>
                    <CodeBlock language="bash">{`export GOOGLE_MAPS_API_KEY="your-api-key"
export DEBUG="true"
fluidmcp run config.json --file --start-server`}</CodeBlock>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Security Best Practices</h3>
                  <ul className="space-y-3 text-sm text-gray-300">
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <div>
                        <strong className="text-white">Never commit secrets:</strong> Use .gitignore for config files with API keys
                      </div>
                    </li>
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <div>
                        <strong className="text-white">Use environment variables:</strong> Keep secrets separate from code
                      </div>
                    </li>
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <div>
                        <strong className="text-white">Enable secure mode:</strong> Require authentication for production deployments
                      </div>
                    </li>
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <div>
                        <strong className="text-white">Rotate credentials:</strong> Regularly update API keys and tokens
                      </div>
                    </li>
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <div>
                        <strong className="text-white">Restrict file permissions:</strong> Token files are automatically set to 600 (owner only)
                      </div>
                    </li>
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <div>
                        <strong className="text-white">Use secret managers:</strong> Consider AWS Secrets Manager or similar for production
                      </div>
                    </li>
                  </ul>
                </div>

                <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-5 flex items-start gap-4">
                  <Key className="h-6 w-6 text-blue-400 mt-1 flex-shrink-0" />
                  <div>
                    <h3 className="font-medium text-base text-white mb-2">Storage Location</h3>
                    <p className="text-sm text-gray-300">
                      Environment variables are stored in the metadata file at:<br />
                      <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400 mt-2 inline-block">
                        ~/.fluidmcp/packages/{"{author}"}/{"{package}"}/{"{version}"}/metadata.json
                      </code>
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Using FluidAI MCP */}
          {activeItem === "using-fluidai-mcp" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">Usage</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Using FluidMCP</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  Learn the core concepts and workflows for managing MCP servers with FluidMCP.
                </p>
              </div>

              <div className="space-y-6">
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Core Workflows</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-center gap-3 mb-3">
                        <div className="h-10 w-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                          <Package className="h-5 w-5 text-blue-400" />
                        </div>
                        <h4 className="font-semibold text-base text-white">Single Package Mode</h4>
                      </div>
                      <p className="text-sm text-gray-300 mb-3">Install and run individual MCP servers:</p>
                      <CodeBlock language="bash">{`# Install a package
fluidmcp install author/package@version

# Run the package
fluidmcp run author/package@version --start-server`}</CodeBlock>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-center gap-3 mb-3">
                        <div className="h-10 w-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                          <FileJson className="h-5 w-5 text-blue-400" />
                        </div>
                        <h4 className="font-semibold text-base text-white">Multi-Server Mode</h4>
                      </div>
                      <p className="text-sm text-gray-300 mb-3">Orchestrate multiple servers from config:</p>
                      <CodeBlock language="bash">{`# Run from configuration file
fluidmcp run config.json --file --start-server

# Run all installed packages
fluidmcp run all --start-server`}</CodeBlock>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Configuration File Structure</h3>
                  <p className="text-sm text-gray-300 mb-4">Create a <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">config.json</code> file to define multiple MCP servers:</p>
                  <CodeBlock language="json">{`{
  "mcpServers": {
    "google-maps": {
      "command": "npx",
      "args": ["-y", "@google-maps/mcp-server"],
      "env": {
        "GOOGLE_MAPS_API_KEY": "your-api-key"
      }
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/files"],
      "env": {}
    },
    "python-server": {
      "command": "python",
      "args": ["-m", "my_mcp_server"],
      "env": {
        "API_KEY": "your-key"
      }
    }
  }
}`}</CodeBlock>
                  
                  <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                    <h4 className="font-semibold text-base text-white mb-3">Configuration Fields</h4>
                    <div className="space-y-3">
                      <div className="flex items-start gap-3 text-sm">
                        <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400 flex-shrink-0">command</code>
                        <span className="text-gray-300">The executable command to run (e.g., npx, python, node)</span>
                      </div>
                      <div className="flex items-start gap-3 text-sm">
                        <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400 flex-shrink-0">args</code>
                        <span className="text-gray-300">Array of command-line arguments</span>
                      </div>
                      <div className="flex items-start gap-3 text-sm">
                        <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400 flex-shrink-0">env</code>
                        <span className="text-gray-300">Environment variables as key-value pairs</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Common Command Options</h3>
                  <div className="space-y-3">
                    <div className="flex items-start gap-4 p-4 rounded-lg border border-[#2A2D36] bg-transparent">
                      <code className="bg-[#1A1D26] px-3 py-1 rounded text-blue-400 flex-shrink-0 text-sm">--start-server</code>
                      <span className="text-sm text-gray-300">Starts the FastAPI gateway server on port 8099</span>
                    </div>
                    <div className="flex items-start gap-4 p-4 rounded-lg border border-[#2A2D36] bg-transparent">
                      <code className="bg-[#1A1D26] px-3 py-1 rounded text-blue-400 flex-shrink-0 text-sm">--file</code>
                      <span className="text-sm text-gray-300">Run from a local configuration file</span>
                    </div>
                    <div className="flex items-start gap-4 p-4 rounded-lg border border-[#2A2D36] bg-transparent">
                      <code className="bg-[#1A1D26] px-3 py-1 rounded text-blue-400 flex-shrink-0 text-sm">--secure</code>
                      <span className="text-sm text-gray-300">Enable bearer token authentication</span>
                    </div>
                    <div className="flex items-start gap-4 p-4 rounded-lg border border-[#2A2D36] bg-transparent">
                      <code className="bg-[#1A1D26] px-3 py-1 rounded text-blue-400 flex-shrink-0 text-sm">--token &lt;token&gt;</code>
                      <span className="text-sm text-gray-300">Specify a custom bearer token for secure mode</span>
                    </div>
                    <div className="flex items-start gap-4 p-4 rounded-lg border border-[#2A2D36] bg-transparent">
                      <code className="bg-[#1A1D26] px-3 py-1 rounded text-blue-400 flex-shrink-0 text-sm">--verbose</code>
                      <span className="text-sm text-gray-300">Enable DEBUG level logging</span>
                    </div>
                    <div className="flex items-start gap-4 p-4 rounded-lg border border-[#2A2D36] bg-transparent">
                      <code className="bg-[#1A1D26] px-3 py-1 rounded text-blue-400 flex-shrink-0 text-sm">--master</code>
                      <span className="text-sm text-gray-300">Use S3-driven configuration management</span>
                    </div>
                    <div className="flex items-start gap-4 p-4 rounded-lg border border-[#2A2D36] bg-transparent">
                      <code className="bg-[#1A1D26] px-3 py-1 rounded text-blue-400 flex-shrink-0 text-sm">--s3</code>
                      <span className="text-sm text-gray-300">Run configuration directly from S3 URL</span>
                    </div>
                  </div>
                </div>

                <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-5">
                  <h3 className="text-lg font-medium mb-3 text-white flex items-center gap-2">
                    <Server className="h-5 w-5 text-blue-400" />
                    S3 Master Mode
                  </h3>
                  <p className="text-sm text-gray-300 mb-4">For centralized configuration management using AWS S3:</p>
                  <CodeBlock language="bash">{`# Set S3 credentials
export S3_BUCKET_NAME="your-bucket"
export S3_ACCESS_KEY="your-access-key"
export S3_SECRET_KEY="your-secret-key"
export S3_REGION="us-east-1"

# Install packages in master mode
fluidmcp install author/package@version --master

# Run all packages from S3 config
fluidmcp run all --master --start-server

# Or run from S3 URL directly
fluidmcp run "https://bucket.s3.amazonaws.com/config.json" --s3 --start-server`}</CodeBlock>
                </div>
              </div>
            </div>
          )}

          {/* Troubleshooting */}
          {activeItem === "troubleshooting" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">Support</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Troubleshooting</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  Diagnose and resolve common issues with FluidMCP.
                </p>
              </div>

              <div className="space-y-6">
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Debugging Steps</h3>
                  
                  <div className="space-y-4">
                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <div className="h-8 w-8 rounded-full bg-blue-500/10 flex items-center justify-center flex-shrink-0">
                          <span className="text-blue-400 font-semibold">1</span>
                        </div>
                        <div>
                          <h4 className="font-semibold text-base text-white mb-2">Enable Verbose Logging</h4>
                          <p className="text-sm text-gray-300 mb-3">Get detailed debug output:</p>
                          <CodeBlock>fluidmcp run config.json --file --start-server --verbose</CodeBlock>
                        </div>
                      </div>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <div className="h-8 w-8 rounded-full bg-blue-500/10 flex items-center justify-center flex-shrink-0">
                          <span className="text-blue-400 font-semibold">2</span>
                        </div>
                        <div>
                          <h4 className="font-semibold text-base text-white mb-2">Check Server Logs</h4>
                          <p className="text-sm text-gray-300 mb-3">View server output and errors:</p>
                          <CodeBlock language="bash">{`# Via API
curl http://localhost:8099/api/servers/my-server/logs?lines=100

# Check status
curl http://localhost:8099/api/servers/my-server/status`}</CodeBlock>
                        </div>
                      </div>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <div className="h-8 w-8 rounded-full bg-blue-500/10 flex items-center justify-center flex-shrink-0">
                          <span className="text-blue-400 font-semibold">3</span>
                        </div>
                        <div>
                          <h4 className="font-semibold text-base text-white mb-2">Validate Configuration</h4>
                          <p className="text-sm text-gray-300 mb-3">Check for config errors:</p>
                          <CodeBlock>fluidmcp validate config.json --file</CodeBlock>
                        </div>
                      </div>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <div className="flex items-start gap-3 mb-3">
                        <div className="h-8 w-8 rounded-full bg-blue-500/10 flex items-center justify-center flex-shrink-0">
                          <span className="text-blue-400 font-semibold">4</span>
                        </div>
                        <div>
                          <h4 className="font-semibold text-base text-white mb-2">Check Health Endpoint</h4>
                          <p className="text-sm text-gray-300 mb-3">Verify gateway is running:</p>
                          <CodeBlock>curl http://localhost:8099/health</CodeBlock>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Log Files</h3>
                  <p className="text-sm text-gray-300 mb-4">FluidMCP logs are stored in:</p>
                  <CodeBlock>~/.fluidmcp/logs/</CodeBlock>
                  
                  <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                    <h4 className="font-semibold text-base text-white mb-3">View Recent Logs</h4>
                    <CodeBlock language="bash">{`# Gateway logs
tail -f ~/.fluidmcp/logs/gateway.log

# Server-specific logs
tail -f ~/.fluidmcp/logs/<server-id>.log`}</CodeBlock>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Network Diagnostics</h3>
                  
                  <div className="space-y-4">
                    <div>
                      <h4 className="font-semibold text-base text-white mb-3">Check if Port is in Use</h4>
                      <CodeBlock language="bash">{`# Linux/Mac
lsof -i :8099

# Check if FluidMCP is running
ps aux | grep fluidmcp`}</CodeBlock>
                    </div>

                    <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                      <h4 className="font-semibold text-base text-white mb-3">Test API Connectivity</h4>
                      <CodeBlock language="bash">{`# Test health endpoint
curl -v http://localhost:8099/health

# Test with authentication
curl -v -H "Authorization: Bearer $(cat ~/.fmcp/tokens/current_token.txt)" \\
  http://localhost:8099/api/servers`}</CodeBlock>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Database Issues</h3>
                  
                  <div className="space-y-4">
                    <div>
                      <h4 className="font-semibold text-base text-white mb-3">Check MongoDB Connection</h4>
                      <p className="text-sm text-gray-300 mb-3">Verify database connectivity:</p>
                      <CodeBlock language="bash">{`# Test MongoDB connection
curl http://localhost:8099/health

# Expected response with database status
{
  "status": "healthy",
  "database": "connected",
  "persistence_enabled": true
}`}</CodeBlock>
                    </div>

                    <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                      <h4 className="font-semibold text-base text-white mb-3">Fallback to In-Memory Mode</h4>
                      <p className="text-sm text-gray-300 mb-3">
                        If MongoDB is unavailable, FluidMCP automatically falls back to in-memory storage.
                        Configuration is not persisted across restarts in this mode.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-5 flex items-start gap-4">
                  <AlertCircle className="h-6 w-6 text-yellow-400 mt-1 flex-shrink-0" />
                  <div>
                    <h3 className="font-medium text-base text-white mb-2">Still Having Issues?</h3>
                    <p className="text-sm text-gray-300 mb-3">
                      Check the <span className="text-blue-400 cursor-pointer hover:underline" onClick={() => handleItemClick("common-issues")}>Common Issues</span> section 
                      or <span className="text-blue-400 cursor-pointer hover:underline" onClick={() => handleItemClick("faq")}>FAQ</span> for specific problems and solutions.
                    </p>
                    <p className="text-sm text-gray-300">
                      For more help, open an issue on <a href="https://github.com/Fluid-AI/fluidmcp" target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline">GitHub</a>.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Common Issues and Solutions */}
          {activeItem === "common-issues" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">Support</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Common Issues and Solutions</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  Quick fixes for frequently encountered problems.
                </p>
              </div>

              <div className="space-y-6">
                {/* Issue 1 */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <div className="flex items-start gap-3 mb-4">
                    <AlertCircle className="h-6 w-6 text-red-400 mt-1 flex-shrink-0" />
                    <div>
                      <h3 className="text-xl font-medium text-white mb-2">Server Fails to Start</h3>
                      <p className="text-sm text-gray-400">Error: "Command not found" or "Failed to start server"</p>
                    </div>
                  </div>
                  
                  <div className="ml-9 space-y-3">
                    <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-4">
                      <h4 className="font-semibold text-sm text-white mb-2">Solution</h4>
                      <ul className="space-y-2 text-sm text-gray-300">
                        <li className="flex items-start gap-2">
                          <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                          <span>Verify the command is installed: <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">which npx</code></span>
                        </li>
                        <li className="flex items-start gap-2">
                          <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                          <span>For npm packages, ensure Node.js 16+ is installed</span>
                        </li>
                        <li className="flex items-start gap-2">
                          <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                          <span>Check server logs: <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">curl http://localhost:8099/api/servers/{"{id}"}/logs</code></span>
                        </li>
                        <li className="flex items-start gap-2">
                          <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                          <span>Try running the command manually to identify the issue</span>
                        </li>
                      </ul>
                    </div>
                  </div>
                </div>

                {/* Issue 2 */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <div className="flex items-start gap-3 mb-4">
                    <AlertCircle className="h-6 w-6 text-red-400 mt-1 flex-shrink-0" />
                    <div>
                      <h3 className="text-xl font-medium text-white mb-2">Port 8099 Already in Use</h3>
                      <p className="text-sm text-gray-400">Error: "Address already in use"</p>
                    </div>
                  </div>
                  
                  <div className="ml-9 space-y-3">
                    <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-4">
                      <h4 className="font-semibold text-sm text-white mb-2">Solution</h4>
                      <CodeBlock language="bash">{`# Find process using port 8099
lsof -i :8099

# Kill the process
kill -9 <PID>

# Or use a different port
export FMCP_PORT=8080
fluidmcp run config.json --file --start-server`}</CodeBlock>
                    </div>
                  </div>
                </div>

                {/* Issue 3 */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <div className="flex items-start gap-3 mb-4">
                    <AlertCircle className="h-6 w-6 text-red-400 mt-1 flex-shrink-0" />
                    <div>
                      <h3 className="text-xl font-medium text-white mb-2">401 Unauthorized Error</h3>
                      <p className="text-sm text-gray-400">API requests return authorization errors</p>
                    </div>
                  </div>
                  
                  <div className="ml-9 space-y-3">
                    <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-4">
                      <h4 className="font-semibold text-sm text-white mb-2">Solution</h4>
                      <ul className="space-y-2 text-sm text-gray-300">
                        <li className="flex items-start gap-2">
                          <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                          <span>Server is running in secure mode - include bearer token in requests</span>
                        </li>
                        <li className="flex items-start gap-2">
                          <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                          <span>Token is stored in: <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">~/.fmcp/tokens/current_token.txt</code></span>
                        </li>
                        <li className="flex items-start gap-2">
                          <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                          <span>Use: <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">-H "Authorization: Bearer $TOKEN"</code></span>
                        </li>
                      </ul>
                    </div>
                  </div>
                </div>

                {/* Issue 4 */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <div className="flex items-start gap-3 mb-4">
                    <AlertCircle className="h-6 w-6 text-red-400 mt-1 flex-shrink-0" />
                    <div>
                      <h3 className="text-xl font-medium text-white mb-2">Environment Variables Not Working</h3>
                      <p className="text-sm text-gray-400">Server can't access API keys or credentials</p>
                    </div>
                  </div>
                  
                  <div className="ml-9 space-y-3">
                    <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-4">
                      <h4 className="font-semibold text-sm text-white mb-2">Solution</h4>
                      <ul className="space-y-2 text-sm text-gray-300">
                        <li className="flex items-start gap-2">
                          <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                          <span>Verify environment variables are set in config: <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">"env": {"{...}"}</code></span>
                        </li>
                        <li className="flex items-start gap-2">
                          <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                          <span>Check for placeholder values that weren't replaced</span>
                        </li>
                        <li className="flex items-start gap-2">
                          <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                          <span>Restart server after updating environment variables</span>
                        </li>
                        <li className="flex items-start gap-2">
                          <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                          <span>Use: <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">fluidmcp edit-env author/package@version</code></span>
                        </li>
                      </ul>
                    </div>
                  </div>
                </div>

                {/* Issue 5 */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <div className="flex items-start gap-3 mb-4">
                    <AlertCircle className="h-6 w-6 text-red-400 mt-1 flex-shrink-0" />
                    <div>
                      <h3 className="text-xl font-medium text-white mb-2">Server Crashes Immediately</h3>
                      <p className="text-sm text-gray-400">Server starts but exits immediately without errors</p>
                    </div>
                  </div>
                  
                  <div className="ml-9 space-y-3">
                    <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-4">
                      <h4 className="font-semibold text-sm text-white mb-2">Solution</h4>
                      <ul className="space-y-2 text-sm text-gray-300">
                        <li className="flex items-start gap-2">
                          <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                          <span>Check server logs for startup errors</span>
                        </li>
                        <li className="flex items-start gap-2">
                          <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                          <span>Verify all required environment variables are set</span>
                        </li>
                        <li className="flex items-start gap-2">
                          <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                          <span>Test the command manually with the same arguments</span>
                        </li>
                        <li className="flex items-start gap-2">
                          <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                          <span>Check if the server expects stdin/stdout stdio transport</span>
                        </li>
                      </ul>
                    </div>
                  </div>
                </div>

                {/* Issue 6 */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <div className="flex items-start gap-3 mb-4">
                    <AlertCircle className="h-6 w-6 text-red-400 mt-1 flex-shrink-0" />
                    <div>
                      <h3 className="text-xl font-medium text-white mb-2">CORS Errors in Browser</h3>
                      <p className="text-sm text-gray-400">Browser blocks API requests due to CORS policy</p>
                    </div>
                  </div>
                  
                  <div className="ml-9 space-y-3">
                    <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-4">
                      <h4 className="font-semibold text-sm text-white mb-2">Solution</h4>
                      <ul className="space-y-2 text-sm text-gray-300">
                        <li className="flex items-start gap-2">
                          <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                          <span>By default, only localhost origins are allowed</span>
                        </li>
                        <li className="flex items-start gap-2">
                          <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                          <span>For production, configure custom allowed origins in code</span>
                        </li>
                        <li className="flex items-start gap-2">
                          <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                          <span>Never use wildcard "*" in production - major security risk</span>
                        </li>
                      </ul>
                    </div>
                  </div>
                </div>

                {/* Issue 7 */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <div className="flex items-start gap-3 mb-4">
                    <AlertCircle className="h-6 w-6 text-red-400 mt-1 flex-shrink-0" />
                    <div>
                      <h3 className="text-xl font-medium text-white mb-2">Package Installation Fails</h3>
                      <p className="text-sm text-gray-400">Error downloading or installing MCP package</p>
                    </div>
                  </div>
                  
                  <div className="ml-9 space-y-3">
                    <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-4">
                      <h4 className="font-semibold text-sm text-white mb-2">Solution</h4>
                      <ul className="space-y-2 text-sm text-gray-300">
                        <li className="flex items-start gap-2">
                          <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                          <span>Check network connectivity and registry access</span>
                        </li>
                        <li className="flex items-start gap-2">
                          <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                          <span>Verify MCP_FETCH_URL and MCP_TOKEN are configured</span>
                        </li>
                        <li className="flex items-start gap-2">
                          <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                          <span>Check if package name and version are correct</span>
                        </li>
                        <li className="flex items-start gap-2">
                          <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                          <span>Use <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">--verbose</code> flag for detailed error messages</span>
                        </li>
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* FAQ */}
          {activeItem === "faq" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">Support</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Frequently Asked Questions</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  Answers to common questions about FluidMCP.
                </p>
              </div>

              <div className="space-y-4">
                {/* FAQ 1 */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-lg font-medium text-white mb-3">What is the Model Context Protocol (MCP)?</h3>
                  <p className="text-sm text-gray-300 leading-relaxed">
                    MCP is an open standard for connecting AI models to external tools and data sources. It provides a unified interface
                    for AI applications to access capabilities like file systems, databases, APIs, and more through standardized "servers"
                    that implement the protocol.
                  </p>
                </div>

                {/* FAQ 2 */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-lg font-medium text-white mb-3">How does FluidMCP differ from other MCP implementations?</h3>
                  <p className="text-sm text-gray-300 leading-relaxed mb-3">
                    FluidMCP is a comprehensive management platform that goes beyond basic MCP clients:
                  </p>
                  <ul className="space-y-2 text-sm text-gray-300">
                    <li className="flex items-start gap-2">
                      <span className="text-blue-400 mt-1">•</span>
                      <span><strong className="text-white">FastAPI Gateway:</strong> RESTful API for programmatic control</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-blue-400 mt-1">•</span>
                      <span><strong className="text-white">Multi-Server Orchestration:</strong> Manage multiple MCP servers simultaneously</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-blue-400 mt-1">•</span>
                      <span><strong className="text-white">Web Dashboard:</strong> Modern UI for monitoring and management</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-blue-400 mt-1">•</span>
                      <span><strong className="text-white">Package Management:</strong> Install and version MCP servers like npm</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-blue-400 mt-1">•</span>
                      <span><strong className="text-white">Production Ready:</strong> Authentication, metrics, logging, and persistence</span>
                    </li>
                  </ul>
                </div>

                {/* FAQ 3 */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-lg font-medium text-white mb-3">Can I use FluidMCP with Claude Desktop?</h3>
                  <p className="text-sm text-gray-300 leading-relaxed">
                    Yes! FluidMCP servers use the standard MCP protocol and can be configured in Claude Desktop's configuration file.
                    You can also use FluidMCP's gateway to manage servers that Claude Desktop connects to via stdio transport.
                  </p>
                </div>

                {/* FAQ 4 */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-lg font-medium text-white mb-3">Is FluidMCP free to use?</h3>
                  <p className="text-sm text-gray-300 leading-relaxed">
                    Yes, FluidMCP is open-source software released under the MIT license. You can use it freely for personal and
                    commercial projects. Enterprise support and hosted solutions are available separately.
                  </p>
                </div>

                {/* FAQ 5 */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-lg font-medium text-white mb-3">What programming languages are supported?</h3>
                  <p className="text-sm text-gray-300 leading-relaxed mb-3">
                    FluidMCP can run MCP servers written in any language that implements the MCP protocol:
                  </p>
                  <ul className="space-y-2 text-sm text-gray-300">
                    <li className="flex items-start gap-2">
                      <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                      <span><strong className="text-white">Python:</strong> Native support for Python-based servers</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                      <span><strong className="text-white">Node.js:</strong> npm packages via npx command</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                      <span><strong className="text-white">Any Language:</strong> As long as it can communicate via stdin/stdout</span>
                    </li>
                  </ul>
                </div>

                {/* FAQ 6 */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-lg font-medium text-white mb-3">Do I need MongoDB to use FluidMCP?</h3>
                  <p className="text-sm text-gray-300 leading-relaxed">
                    No, MongoDB is optional. FluidMCP automatically falls back to in-memory storage if MongoDB is not available.
                    However, for production deployments where you want configuration persistence across restarts, MongoDB is recommended.
                  </p>
                </div>

                {/* FAQ 7 */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-lg font-medium text-white mb-3">How do I secure my FluidMCP deployment?</h3>
                  <p className="text-sm text-gray-300 leading-relaxed mb-3">
                    FluidMCP includes several security features:
                  </p>
                  <ul className="space-y-2 text-sm text-gray-300">
                    <li className="flex items-start gap-2">
                      <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                      <span>Enable <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">--secure</code> mode for bearer token authentication</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                      <span>Configure CORS to restrict allowed origins</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                      <span>Use environment variables for secrets (never hardcode in config)</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                      <span>Deploy behind a reverse proxy with HTTPS</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                      <span>Regularly rotate API keys and tokens</span>
                    </li>
                  </ul>
                </div>

                {/* FAQ 8 */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-lg font-medium text-white mb-3">Can I run FluidMCP in Docker?</h3>
                  <p className="text-sm text-gray-300 leading-relaxed mb-3">
                    Yes! FluidMCP includes a Dockerfile for containerized deployments:
                  </p>
                  <CodeBlock language="bash">{`docker build -t fluidmcp .
docker run -p 8099:8099 fluidmcp`}</CodeBlock>
                </div>

                {/* FAQ 9 */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-lg font-medium text-white mb-3">What is S3 Master Mode?</h3>
                  <p className="text-sm text-gray-300 leading-relaxed">
                    S3 Master Mode enables centralized configuration management using AWS S3 as the source of truth. Multiple FluidMCP
                    instances can pull configuration from the same S3 bucket, enabling distributed deployments with synchronized
                    configuration. Useful for enterprise multi-region deployments.
                  </p>
                </div>

                {/* FAQ 10 */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-lg font-medium text-white mb-3">How do I monitor FluidMCP in production?</h3>
                  <p className="text-sm text-gray-300 leading-relaxed mb-3">
                    FluidMCP provides comprehensive monitoring capabilities:
                  </p>
                  <ul className="space-y-2 text-sm text-gray-300">
                    <li className="flex items-start gap-2">
                      <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                      <span><strong className="text-white">/health:</strong> Health check endpoint for load balancers</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                      <span><strong className="text-white">/metrics:</strong> Prometheus-compatible metrics</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                      <span><strong className="text-white">Server Logs:</strong> Real-time log streaming via API</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <CheckCircle className="h-4 w-4 text-blue-400 mt-1 flex-shrink-0" />
                      <span><strong className="text-white">Web Dashboard:</strong> Visual monitoring and management</span>
                    </li>
                  </ul>
                </div>

                {/* FAQ 11 */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-lg font-medium text-white mb-3">Where can I find MCP servers to use with FluidMCP?</h3>
                  <p className="text-sm text-gray-300 leading-relaxed mb-3">
                    MCP servers are available from several sources:
                  </p>
                  <ul className="space-y-2 text-sm text-gray-300">
                    <li className="flex items-start gap-2">
                      <span className="text-blue-400 mt-1">•</span>
                      <span><a href="https://github.com/modelcontextprotocol/servers" target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline">Official MCP Servers Repository</a></span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-blue-400 mt-1">•</span>
                      <span>npm registry (search for "@modelcontextprotocol")</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-blue-400 mt-1">•</span>
                      <span>FluidMCP registry (enterprise feature)</span>
                    </li>
                    <li className="flex items-start gap-2">
                      <span className="text-blue-400 mt-1">•</span>
                      <span>Build your own using MCP SDKs</span>
                    </li>
                  </ul>
                </div>

                {/* FAQ 12 */}
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-lg font-medium text-white mb-3">How do I contribute to FluidMCP?</h3>
                  <p className="text-sm text-gray-300 leading-relaxed">
                    Contributions are welcome! Check out the{" "}
                    <a href="https://github.com/Fluid-AI/fluidmcp/blob/main/CONTRIBUTING.md" target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline">
                      CONTRIBUTING.md
                    </a>{" "}
                    file in the repository for guidelines. You can contribute by reporting bugs, suggesting features, improving
                    documentation, or submitting pull requests.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Example API Call */}
          {activeItem === "example-call" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">API</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Example API Call</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  Practical examples of using the FluidMCP API in various scenarios.
                </p>
              </div>

              <div className="space-y-6">
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Adding and Starting a Server</h3>
                  <p className="text-sm text-gray-300 mb-4">Complete workflow to add and start a new MCP server:</p>
                  <CodeBlock language="bash">{`# Step 1: Add server configuration
curl -X POST http://localhost:8099/api/servers \\
  -H "Content-Type: application/json" \\
  -d '{
    "id": "filesystem",
    "name": "Filesystem Server",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    "env": {}
  }'

# Step 2: Start the server
curl -X POST http://localhost:8099/api/servers/filesystem/start

# Step 3: Check server status
curl http://localhost:8099/api/servers/filesystem/status`}</CodeBlock>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Calling MCP Tools</h3>
                  <p className="text-sm text-gray-300 mb-4">Execute MCP tools via the dynamic router:</p>
                  <CodeBlock language="python">{`import requests
import json

# MCP JSON-RPC request
url = "http://localhost:8099/filesystem/mcp"
payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "read_file",
        "arguments": {
            "path": "/tmp/example.txt"
        }
    }
}

response = requests.post(url, json=payload)
print(json.dumps(response.json(), indent=2))`}</CodeBlock>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Using Server-Sent Events (SSE)</h3>
                  <p className="text-sm text-gray-300 mb-4">Stream responses from MCP servers:</p>
                  <CodeBlock language="bash">{`curl -N -X POST http://localhost:8099/filesystem/sse \\
  -H "Content-Type: application/json" \\
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "list_directory",
        "arguments": {"path": "/tmp"}
    }
  }'`}</CodeBlock>
                  <p className="text-sm text-gray-400 mt-4">
                    SSE endpoints return <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">text/event-stream</code> with real-time updates.
                  </p>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Managing Environment Variables</h3>
                  <p className="text-sm text-gray-300 mb-4">Update API keys and configuration:</p>
                  <CodeBlock language="bash">{`# Update environment variables
curl -X PUT http://localhost:8099/api/servers/google-maps/instance/env \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer YOUR_TOKEN" \\
  -d '{
    "GOOGLE_MAPS_API_KEY": "new-api-key-value"
  }'

# Get environment variable status
curl http://localhost:8099/api/servers/google-maps/instance/env`}</CodeBlock>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Python SDK Example</h3>
                  <p className="text-sm text-gray-300 mb-4">Complete Python script using the API:</p>
                  <CodeBlock language="python">{`import requests
from typing import Optional

class FluidMCPClient:
    def __init__(self, base_url: str = "http://localhost:8099", token: Optional[str] = None):
        self.base_url = base_url
        self.headers = {"Content-Type": "application/json"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
    
    def list_servers(self):
        response = requests.get(f"{self.base_url}/api/servers", headers=self.headers)
        return response.json()
    
    def start_server(self, server_id: str):
        response = requests.post(
            f"{self.base_url}/api/servers/{server_id}/start",
            headers=self.headers
        )
        return response.json()
    
    def call_tool(self, server_id: str, tool_name: str, arguments: dict):
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        response = requests.post(
            f"{self.base_url}/{server_id}/mcp",
            json=payload
        )
        return response.json()

# Usage
client = FluidMCPClient(token="your-token-here")

# List all servers
servers = client.list_servers()
print(f"Servers: {servers}")

# Start a server
result = client.start_server("filesystem")
print(f"Started: {result}")

# Call a tool
result = client.call_tool(
    "filesystem",
    "read_file",
    {"path": "/tmp/test.txt"}
)
print(f"Result: {result}")`}</CodeBlock>
                </div>
              </div>
            </div>
          )}

          {/* Managing API Keys */}
          {activeItem === "managing-keys" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">API</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Managing API Keys</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  Secure management of API keys and environment variables for MCP servers.
                </p>
              </div>

              <div className="space-y-6">
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Local Environment Variables</h3>
                  <p className="text-sm text-gray-300 mb-4">Edit environment variables for installed packages:</p>
                  <CodeBlock>fluidmcp edit-env author/package@version</CodeBlock>
                  <p className="text-sm text-gray-400 mt-4">
                    Opens an interactive editor where you can securely configure environment variables.
                    Values are stored in the package's metadata.json file.
                  </p>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Via Management API</h3>
                  <p className="text-sm text-gray-300 mb-4">Update environment variables programmatically:</p>
                  <CodeBlock language="bash">{`# Update environment variables (requires authentication)
curl -X PUT http://localhost:8099/api/servers/my-server/instance/env \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer YOUR_TOKEN" \\
  -d '{
    "API_KEY": "new-key",
    "DEBUG": "true"
  }'`}</CodeBlock>
                  
                  <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                    <h4 className="font-semibold text-base text-white mb-3">Get Environment Status</h4>
                    <p className="text-sm text-gray-300 mb-3">View which variables are configured (values are masked):</p>
                    <CodeBlock language="bash">curl http://localhost:8099/api/servers/my-server/instance/env</CodeBlock>
                    <p className="text-sm text-gray-400 mt-3">Returns metadata with masked values for security.</p>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Bearer Token Management</h3>
                  <p className="text-sm text-gray-300 mb-4">Manage FluidMCP authentication tokens:</p>
                  <CodeBlock language="bash">{`# Generate new token
fluidmcp token regenerate

# View current token
fluidmcp token show

# Clear saved token
fluidmcp token clear`}</CodeBlock>
                  
                  <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                    <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-4">
                      <h4 className="text-sm font-semibold text-white mb-2">Token Storage</h4>
                      <p className="text-sm text-gray-300">
                        Tokens are stored at <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">~/.fmcp/tokens/current_token.txt</code> with 
                        permissions <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">600</code> (owner read/write only).
                      </p>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Environment Variable Security</h3>
                  <ul className="space-y-4 text-sm text-gray-300">
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <span><strong className="text-white">Validation:</strong> All environment variables are validated to prevent injection attacks</span>
                    </li>
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <span><strong className="text-white">Masking:</strong> API endpoints return masked values (****) for security</span>
                    </li>
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <span><strong className="text-white">No Shell Execution:</strong> Values are passed directly to processes, preventing shell injection</span>
                    </li>
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <span><strong className="text-white">Length Limits:</strong> Maximum 10KB per variable to prevent DoS attacks</span>
                    </li>
                  </ul>
                </div>

                <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-5 flex items-start gap-4">
                  <AlertCircle className="h-6 w-6 text-yellow-400 mt-1 flex-shrink-0" />
                  <div>
                    <h3 className="font-medium text-base text-white mb-2">Security Best Practices</h3>
                    <ul className="space-y-2 text-sm text-gray-300">
                      <li>• Never commit API keys to version control</li>
                      <li>• Use environment variables for production deployments</li>
                      <li>• Enable secure mode (--secure) for remote deployments</li>
                      <li>• Rotate tokens regularly using <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">fluidmcp token regenerate</code></li>
                      <li>• Use restrictive file permissions for config files</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Troubleshooting */}
          {activeItem === "troubleshooting" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">Support</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Troubleshooting</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  Common troubleshooting steps and debugging techniques for FluidMCP.
                </p>
              </div>

              <div className="space-y-6">
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Enable Verbose Logging</h3>
                  <p className="text-sm text-gray-300 mb-4">Get detailed debug information:</p>
                  <CodeBlock language="bash">{`# Enable verbose mode for any command
fluidmcp run config.json --file --start-server --verbose

# Check logs for a specific server
curl http://localhost:8099/api/servers/my-server/logs?lines=100`}</CodeBlock>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Validate Configuration</h3>
                  <p className="text-sm text-gray-300 mb-4">Check configuration before running:</p>
                  <CodeBlock language="bash">{`# Validate config file
fluidmcp validate config.json --file

# Validate installed package
fluidmcp validate author/package@version`}</CodeBlock>
                  
                  <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                    <h4 className="font-semibold text-base text-white mb-3">Validation Checks</h4>
                    <ul className="space-y-2 text-sm text-gray-300">
                      <li>• Configuration file structure and syntax</li>
                      <li>• Command availability in system PATH</li>
                      <li>• Required environment variables</li>
                      <li>• Metadata file existence</li>
                    </ul>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Server Health Check</h3>
                  <p className="text-sm text-gray-300 mb-4">Monitor server health and database connectivity:</p>
                  <CodeBlock language="bash">{`# Check overall health
curl http://localhost:8099/health

# Get specific server status
curl http://localhost:8099/api/servers/my-server/status

# View Prometheus metrics
curl http://localhost:8099/metrics`}</CodeBlock>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Debugging Server Startup Issues</h3>
                  <div className="space-y-4">
                    <div className="border-l-4 border-blue-500 pl-4 py-2">
                      <h4 className="font-semibold text-base text-white mb-2">Check Command Availability</h4>
                      <CodeBlock language="bash">{`# Verify command exists
which npx
which python
which node`}</CodeBlock>
                    </div>

                    <div className="border-l-4 border-blue-500 pl-4 py-2">
                      <h4 className="font-semibold text-base text-white mb-2">Verify Environment Variables</h4>
                      <CodeBlock language="bash">{`# Check env var status
curl http://localhost:8099/api/servers/my-server/instance/env

# Edit environment variables
fluidmcp edit-env author/package@version`}</CodeBlock>
                    </div>

                    <div className="border-l-4 border-blue-500 pl-4 py-2">
                      <h4 className="font-semibold text-base text-white mb-2">Check Server Logs</h4>
                      <CodeBlock language="bash">{`# Get recent logs
curl http://localhost:8099/api/servers/my-server/logs?lines=50`}</CodeBlock>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Port Already in Use</h3>
                  <p className="text-sm text-gray-300 mb-4">If port 8099 is already in use:</p>
                  <CodeBlock language="bash">{`# Set custom port via environment variable
export FMCP_PORT=8080
fluidmcp run config.json --file --start-server

# Or find process using port 8099
lsof -i :8099
kill -9 <PID>`}</CodeBlock>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Database Connection Issues</h3>
                  <p className="text-sm text-gray-300 mb-4">FluidMCP can run with or without MongoDB:</p>
                  <div className="space-y-3 text-sm text-gray-300">
                    <div className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <span><strong className="text-white">With MongoDB:</strong> Persistent storage for configurations and logs</span>
                    </div>
                    <div className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <span><strong className="text-white">Without MongoDB:</strong> In-memory storage (configurations lost on restart)</span>
                    </div>
                  </div>
                  <p className="text-sm text-gray-400 mt-4">
                    Check <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">/health</code> endpoint for database status.
                  </p>
                </div>

                <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-5">
                  <h3 className="text-lg font-medium mb-3 text-white flex items-center gap-2">
                    <HelpCircle className="h-5 w-5 text-blue-400" />
                    Getting Help
                  </h3>
                  <p className="text-sm text-gray-300 mb-3">If you're still experiencing issues:</p>
                  <ul className="space-y-2 text-sm text-gray-300">
                    <li>• Check the GitHub Issues: <a href="https://github.com/Fluid-AI/fluidmcp/issues" className="text-blue-400 hover:underline">github.com/Fluid-AI/fluidmcp/issues</a></li>
                    <li>• Run with <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">--verbose</code> and share logs</li>
                    <li>• Include your configuration file (remove sensitive values)</li>
                    <li>• Specify your Python version and OS</li>
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* Common Issues and Solutions */}
          {activeItem === "common-issues" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">Support</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Common Issues and Solutions</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  Quick solutions to frequently encountered problems.
                </p>
              </div>

              <div className="space-y-6">
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white flex items-center gap-2">
                    <AlertCircle className="h-6 w-6 text-red-400" />
                    Command Not Found
                  </h3>
                  <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-4">
                    <p className="text-sm text-gray-300 font-mono">Error: Command 'npx' not found in PATH</p>
                  </div>
                  <div className="space-y-3">
                    <p className="text-sm text-gray-300"><strong className="text-white">Solution:</strong></p>
                    <CodeBlock language="bash">{`# Install Node.js and npm
sudo apt install nodejs npm  # Ubuntu/Debian
brew install node            # macOS

# Verify installation
which npx
npx --version`}</CodeBlock>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white flex items-center gap-2">
                    <AlertCircle className="h-6 w-6 text-red-400" />
                    Missing Environment Variables
                  </h3>
                  <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-4">
                    <p className="text-sm text-gray-300 font-mono">Missing required env var 'API_KEY' (server: my-server)</p>
                  </div>
                  <div className="space-y-3">
                    <p className="text-sm text-gray-300"><strong className="text-white">Solution:</strong></p>
                    <CodeBlock language="bash">{`# Option 1: Edit via CLI
fluidmcp edit-env author/package@version

# Option 2: Set in environment
export API_KEY="your-api-key"

# Option 3: Update via API
curl -X PUT http://localhost:8099/api/servers/my-server/instance/env \\
  -H "Content-Type: application/json" \\
  -d '{"API_KEY": "your-key"}'`}</CodeBlock>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white flex items-center gap-2">
                    <AlertCircle className="h-6 w-6 text-red-400" />
                    Server Won't Start
                  </h3>
                  <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-4">
                    <p className="text-sm text-gray-300 font-mono">Failed to start server 'my-server'</p>
                  </div>
                  <div className="space-y-3">
                    <p className="text-sm text-gray-300"><strong className="text-white">Troubleshooting steps:</strong></p>
                    <ol className="space-y-3 list-decimal list-inside text-sm text-gray-300">
                      <li>Check server logs: <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">curl http://localhost:8099/api/servers/my-server/logs</code></li>
                      <li>Validate configuration: <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">fluidmcp validate my-server</code></li>
                      <li>Verify command exists: <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">which npx</code></li>
                      <li>Check environment variables are set</li>
                      <li>Try running with <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">--verbose</code> flag</li>
                    </ol>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white flex items-center gap-2">
                    <AlertCircle className="h-6 w-6 text-red-400" />
                    401 Unauthorized
                  </h3>
                  <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-4">
                    <p className="text-sm text-gray-300 font-mono">Invalid or missing authorization token</p>
                  </div>
                  <div className="space-y-3">
                    <p className="text-sm text-gray-300"><strong className="text-white">Solution:</strong></p>
                    <CodeBlock language="bash">{`# Check if server is running in secure mode
curl http://localhost:8099/health

# Get current token
fluidmcp token show

# Include token in requests
curl -H "Authorization: Bearer YOUR_TOKEN" \\
  http://localhost:8099/api/servers`}</CodeBlock>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white flex items-center gap-2">
                    <AlertCircle className="h-6 w-6 text-red-400" />
                    Package Installation Fails
                  </h3>
                  <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-4">
                    <p className="text-sm text-gray-300 font-mono">Failed to install package author/package@version</p>
                  </div>
                  <div className="space-y-3">
                    <p className="text-sm text-gray-300"><strong className="text-white">Common causes:</strong></p>
                    <ul className="space-y-2 text-sm text-gray-300">
                      <li>• Package not found in registry - verify name and version</li>
                      <li>• Network connectivity issues - check internet connection</li>
                      <li>• Missing dependencies - install required system packages</li>
                      <li>• Permission issues - check write access to <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">~/.fluidmcp/</code></li>
                    </ul>
                    <CodeBlock language="bash">{`# Try with verbose mode for more details
fluidmcp install author/package@version --verbose`}</CodeBlock>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white flex items-center gap-2">
                    <AlertCircle className="h-6 w-6 text-red-400" />
                    CORS Errors in Browser
                  </h3>
                  <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-4">
                    <p className="text-sm text-gray-300 font-mono">Access blocked by CORS policy</p>
                  </div>
                  <div className="space-y-3">
                    <p className="text-sm text-gray-300"><strong className="text-white">Solution:</strong></p>
                    <p className="text-sm text-gray-300">FluidMCP uses secure CORS defaults (localhost only). For custom origins:</p>
                    <CodeBlock language="python">{`# Configure allowed origins in your code
app = await create_app(
    db_manager=db_manager,
    server_manager=server_manager,
    allowed_origins=[
        "http://localhost:3000",
        "https://yourdomain.com"
    ]
)`}</CodeBlock>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white flex items-center gap-2">
                    <AlertCircle className="h-6 w-6 text-red-400" />
                    High Memory Usage
                  </h3>
                  <div className="space-y-3">
                    <p className="text-sm text-gray-300"><strong className="text-white">Causes and solutions:</strong></p>
                    <ul className="space-y-3 text-sm text-gray-300">
                      <li className="flex items-start gap-3">
                        <span className="text-blue-400 mt-1">•</span>
                        <span><strong className="text-white">Multiple servers:</strong> Each MCP server runs as a separate process. Stop unused servers.</span>
                      </li>
                      <li className="flex items-start gap-3">
                        <span className="text-blue-400 mt-1">•</span>
                        <span><strong className="text-white">Log accumulation:</strong> Logs are stored in memory. Limit log lines in queries.</span>
                      </li>
                      <li className="flex items-start gap-3">
                        <span className="text-blue-400 mt-1">•</span>
                        <span><strong className="text-white">vLLM models:</strong> LLM models require significant GPU/CPU memory. Use smaller models or reduce batch size.</span>
                      </li>
                    </ul>
                    <CodeBlock language="bash">{`# Stop unused servers
curl -X POST http://localhost:8099/api/servers/my-server/stop

# Or stop all
curl -X POST http://localhost:8099/api/servers/stop-all`}</CodeBlock>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* FAQ */}
          {activeItem === "faq" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">Support</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Frequently Asked Questions</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  Answers to common questions about FluidMCP.
                </p>
              </div>

              <div className="space-y-6">
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-xl font-medium mb-3 text-white">What is FluidMCP?</h3>
                  <p className="text-sm text-gray-300">
                    FluidMCP is a CLI tool and FastAPI gateway for managing multiple Model Context Protocol (MCP) servers. 
                    It allows you to install, configure, and run MCP servers from a single unified interface, making it easy to 
                    integrate various tools and data sources into your AI applications.
                  </p>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-xl font-medium mb-3 text-white">Do I need MongoDB to use FluidMCP?</h3>
                  <p className="text-sm text-gray-300 mb-3">
                    No, MongoDB is optional. FluidMCP can run in two modes:
                  </p>
                  <ul className="space-y-2 text-sm text-gray-300">
                    <li>• <strong className="text-white">With MongoDB:</strong> Persistent storage for configurations, logs, and server state</li>
                    <li>• <strong className="text-white">Without MongoDB:</strong> In-memory storage (configurations are lost on restart)</li>
                  </ul>
                  <p className="text-sm text-gray-400 mt-3">
                    Check the <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">/health</code> endpoint to see if database persistence is enabled.
                  </p>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-xl font-medium mb-3 text-white">Can I run FluidMCP in production?</h3>
                  <p className="text-sm text-gray-300 mb-3">
                    Yes! For production deployments:
                  </p>
                  <ul className="space-y-2 text-sm text-gray-300">
                    <li>• Enable secure mode with <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">--secure --token</code></li>
                    <li>• Configure CORS allowed origins (don't use wildcards)</li>
                    <li>• Use MongoDB for persistence</li>
                    <li>• Set up Prometheus monitoring via <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">/metrics</code></li>
                    <li>• Use environment variables for API keys</li>
                    <li>• Consider running behind a reverse proxy (nginx, traefik)</li>
                  </ul>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-xl font-medium mb-3 text-white">What's the difference between --file and --master modes?</h3>
                  <p className="text-sm text-gray-300 mb-3">
                    <strong className="text-white">--file mode:</strong> Runs from a local configuration file on your machine.
                  </p>
                  <p className="text-sm text-gray-300 mb-3">
                    <strong className="text-white">--master mode:</strong> Uses S3 for centralized configuration management. Useful for:
                  </p>
                  <ul className="space-y-2 text-sm text-gray-300">
                    <li>• Multi-environment deployments</li>
                    <li>• Team collaboration</li>
                    <li>• Centralized config updates</li>
                  </ul>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-xl font-medium mb-3 text-white">How do I update FluidMCP?</h3>
                  <CodeBlock language="bash">{`# Update via pip
pip install --upgrade fluidmcp

# Verify new version
fluidmcp --version`}</CodeBlock>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-xl font-medium mb-3 text-white">Can I create my own MCP server?</h3>
                  <p className="text-sm text-gray-300 mb-3">
                    Yes! Follow the MCP specification to create custom servers. Once created, you can:
                  </p>
                  <ul className="space-y-2 text-sm text-gray-300">
                    <li>• Add it to FluidMCP config.json with appropriate command and args</li>
                    <li>• Install dependencies via npm, pip, or other package managers</li>
                    <li>• Manage it through FluidMCP like any other server</li>
                  </ul>
                  <p className="text-sm text-gray-400 mt-3">
                    See the official MCP documentation for server development guidelines.
                  </p>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-xl font-medium mb-3 text-white">What port does FluidMCP use?</h3>
                  <p className="text-sm text-gray-300 mb-3">
                    FluidMCP uses port <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">8099</code> by default. To use a different port:
                  </p>
                  <CodeBlock language="bash">{`export FMCP_PORT=8080
fluidmcp run config.json --file --start-server`}</CodeBlock>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-xl font-medium mb-3 text-white">How do I contribute to FluidMCP?</h3>
                  <p className="text-sm text-gray-300 mb-3">
                    We welcome contributions! Here's how to get started:
                  </p>
                  <ol className="space-y-2 list-decimal list-inside text-sm text-gray-300">
                    <li>Fork the repository on GitHub</li>
                    <li>Clone your fork and create a feature branch</li>
                    <li>Make your changes and add tests</li>
                    <li>Submit a pull request</li>
                  </ol>
                  <p className="text-sm text-gray-400 mt-3">
                    See <a href="https://github.com/Fluid-AI/fluidmcp/blob/main/CONTRIBUTING.md" className="text-blue-400 hover:underline">CONTRIBUTING.md</a> for detailed guidelines.
                  </p>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-xl font-medium mb-3 text-white">Is FluidMCP free to use?</h3>
                  <p className="text-sm text-gray-300">
                    Yes! FluidMCP is open source and licensed under the GNU General Public License v3.0. 
                    You can use it freely for both personal and commercial projects.
                  </p>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-xl font-medium mb-3 text-white">Where can I get help?</h3>
                  <p className="text-sm text-gray-300 mb-3">
                    If you need assistance:
                  </p>
                  <ul className="space-y-2 text-sm text-gray-300">
                    <li>• Check this documentation first</li>
                    <li>• Search existing <a href="https://github.com/Fluid-AI/fluidmcp/issues" className="text-blue-400 hover:underline">GitHub Issues</a></li>
                    <li>• Open a new issue with detailed information</li>
                    <li>• Include logs (run with <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">--verbose</code>)</li>
                  </ul>
                </div>

                <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-5">
                  <h3 className="text-lg font-medium mb-3 text-white flex items-center gap-2">
                    <HelpCircle className="h-5 w-5 text-blue-400" />
                    Still Have Questions?
                  </h3>
                  <p className="text-sm text-gray-300 mb-3">
                    If your question isn't answered here, please:
                  </p>
                  <ul className="space-y-2 text-sm text-gray-300">
                    <li>• Open an issue on GitHub: <a href="https://github.com/Fluid-AI/fluidmcp/issues" className="text-blue-400 hover:underline">github.com/Fluid-AI/fluidmcp/issues</a></li>
                    <li>• Check the troubleshooting guide in this documentation</li>
                    <li>• Review the examples in the repository</li>
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* Example API Call */}
          {activeItem === "example-call" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">API</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Example API Call</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  Practical examples of interacting with the FluidMCP API using various tools and languages.
                </p>
              </div>

              <div className="space-y-6">
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Using cURL</h3>
                  
                  <div className="space-y-5">
                    <div>
                      <h4 className="font-semibold text-base text-white mb-3">Add a Server</h4>
                      <CodeBlock language="bash">{`curl -X POST http://localhost:8099/api/servers \\
  -H "Content-Type: application/json" \\
  -d '{
    "id": "my-server",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    "env": {
      "DEBUG": "true"
    }
  }'`}</CodeBlock>
                    </div>

                    <div>
                      <h4 className="font-semibold text-base text-white mb-3">Start the Server</h4>
                      <CodeBlock language="bash">curl -X POST http://localhost:8099/api/servers/my-server/start</CodeBlock>
                    </div>

                    <div>
                      <h4 className="font-semibold text-base text-white mb-3">Get Server Status</h4>
                      <CodeBlock language="bash">curl http://localhost:8099/api/servers/my-server/status</CodeBlock>
                    </div>

                    <div>
                      <h4 className="font-semibold text-base text-white mb-3">List Available Tools</h4>
                      <CodeBlock language="bash">curl http://localhost:8099/api/servers/my-server/tools</CodeBlock>
                    </div>

                    <div>
                      <h4 className="font-semibold text-base text-white mb-3">Execute a Tool</h4>
                      <CodeBlock language="bash">{`curl -X POST http://localhost:8099/api/servers/my-server/tools/read_file/run \\
  -H "Content-Type: application/json" \\
  -d '{
    "arguments": {
      "path": "/tmp/example.txt"
    }
  }'`}</CodeBlock>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Using Python Requests</h3>
                  <CodeBlock language="python">{`import requests

BASE_URL = "http://localhost:8099"

# Add and start a server
config = {
    "id": "my-server",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    "env": {"DEBUG": "true"}
}

response = requests.post(f"{BASE_URL}/api/servers", json=config)
print(f"Server added: {response.json()}")

response = requests.post(f"{BASE_URL}/api/servers/my-server/start")
print(f"Server started: {response.json()}")

# List available tools
response = requests.get(f"{BASE_URL}/api/servers/my-server/tools")
tools = response.json()["tools"]
print(f"Available tools: {[t['name'] for t in tools]}")

# Execute a tool
response = requests.post(
    f"{BASE_URL}/api/servers/my-server/tools/read_file/run",
    json={"arguments": {"path": "/tmp/example.txt"}}
)
print(f"Tool result: {response.json()}")`}</CodeBlock>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">With Authentication</h3>
                  <p className="text-sm text-gray-300 mb-4">When running in secure mode, include the bearer token:</p>
                  <CodeBlock language="bash">{`# Export token
export TOKEN="your-bearer-token"

# Make authenticated request
curl -H "Authorization: Bearer $TOKEN" \\
  http://localhost:8099/api/servers`}</CodeBlock>
                  
                  <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                    <h4 className="font-semibold text-base text-white mb-3">Python with Auth</h4>
                    <CodeBlock language="python">{`import requests

TOKEN = "your-bearer-token"
headers = {"Authorization": f"Bearer {TOKEN}"}

response = requests.get(
    "http://localhost:8099/api/servers",
    headers=headers
)
servers = response.json()`}</CodeBlock>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">TypeScript/JavaScript Example</h3>
                  <CodeBlock language="typescript">{`const BASE_URL = 'http://localhost:8099';

async function addServer() {
  const config = {
    id: 'my-server',
    command: 'npx',
    args: ['-y', '@modelcontextprotocol/server-filesystem', '/tmp'],
    env: { DEBUG: 'true' }
  };

  const response = await fetch(\`\${BASE_URL}/api/servers\`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config)
  });

  return response.json();
}

async function getTools(serverId: string) {
  const response = await fetch(\`\${BASE_URL}/api/servers/\${serverId}/tools\`);
  const data = await response.json();
  return data.tools;
}

async function executeTool(serverId: string, toolName: string, args: any) {
  const response = await fetch(
    \`\${BASE_URL}/api/servers/\${serverId}/tools/\${toolName}/run\`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ arguments: args })
    }
  );
  return response.json();
}`}</CodeBlock>
                </div>
              </div>
            </div>
          )}

          {/* Managing API Keys */}
          {activeItem === "managing-keys" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">API</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Managing API Keys</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  Best practices for managing API keys, environment variables, and authentication tokens in FluidMCP.
                </p>
              </div>

              <div className="space-y-6">
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Token Management Commands</h3>
                  <p className="text-sm text-gray-300 mb-4">FluidMCP provides built-in token management commands:</p>
                  
                  <div className="space-y-4">
                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <h4 className="font-semibold text-base text-white mb-3">Show Current Token</h4>
                      <p className="text-sm text-gray-300 mb-3">Display the saved bearer token:</p>
                      <CodeBlock>fluidmcp token show</CodeBlock>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <h4 className="font-semibold text-base text-white mb-3">Generate New Token</h4>
                      <p className="text-sm text-gray-300 mb-3">Create and save a new bearer token:</p>
                      <CodeBlock>fluidmcp token regenerate</CodeBlock>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <h4 className="font-semibold text-base text-white mb-3">Clear Token</h4>
                      <p className="text-sm text-gray-300 mb-3">Remove the saved token:</p>
                      <CodeBlock>fluidmcp token clear</CodeBlock>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Environment Variable Management</h3>
                  <p className="text-sm text-gray-300 mb-4">Securely manage environment variables for your MCP servers:</p>
                  
                  <div className="space-y-4">
                    <div>
                      <h4 className="font-semibold text-base text-white mb-3">Interactive Editor</h4>
                      <CodeBlock>fluidmcp edit-env author/package@version</CodeBlock>
                      <p className="text-sm text-gray-400 mt-3">Opens an interactive editor to configure environment variables.</p>
                    </div>

                    <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                      <h4 className="font-semibold text-base text-white mb-3">Via Configuration File</h4>
                      <CodeBlock language="json">{`{
  "mcpServers": {
    "my-server": {
      "command": "npx",
      "args": ["-y", "@google-maps/mcp-server"],
      "env": {
        "GOOGLE_MAPS_API_KEY": {
          "required": true,
          "value": ""
        },
        "DEBUG": {
          "required": false,
          "value": "true"
        }
      }
    }
  }
}`}</CodeBlock>
                      <p className="text-sm text-gray-400 mt-3">
                        Set <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">required: true</code> for mandatory variables.
                        Leave <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">value</code> empty to load from system environment.
                      </p>
                    </div>

                    <div className="mt-5 pt-5 border-t border-[#2A2D36]">
                      <h4 className="font-semibold text-base text-white mb-3">Via API</h4>
                      <CodeBlock language="bash">{`# Update environment variables
curl -X PUT http://localhost:8099/api/servers/my-server/instance/env \\
  -H "Content-Type: application/json" \\
  -d '{
    "API_KEY": "new-value",
    "DEBUG": "true"
  }'

# Get environment variables (masked)
curl http://localhost:8099/api/servers/my-server/instance/env

# Delete specific variables
curl -X DELETE http://localhost:8099/api/servers/my-server/instance/env \\
  -H "Content-Type: application/json" \\
  -d '{"keys": ["OLD_API_KEY"]}'`}</CodeBlock>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Security Best Practices</h3>
                  <ul className="space-y-4">
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <div>
                        <strong className="text-white">Never commit secrets:</strong> Add config files with API keys to <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">.gitignore</code>
                      </div>
                    </li>
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <div>
                        <strong className="text-white">Use environment variables:</strong> Keep secrets separate from code
                      </div>
                    </li>
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <div>
                        <strong className="text-white">Enable secure mode:</strong> Always use <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">--secure</code> in production
                      </div>
                    </li>
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <div>
                        <strong className="text-white">Rotate credentials:</strong> Regularly update API keys and tokens using <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">fluidmcp token regenerate</code>
                      </div>
                    </li>
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <div>
                        <strong className="text-white">File permissions:</strong> Token files are automatically set to <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">600</code> (owner only)
                      </div>
                    </li>
                    <li className="flex items-start gap-3">
                      <CheckCircle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
                      <div>
                        <strong className="text-white">Use secret managers:</strong> Consider AWS Secrets Manager or HashiCorp Vault for production deployments
                      </div>
                    </li>
                  </ul>
                </div>

                <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-5 flex items-start gap-4">
                  <Key className="h-6 w-6 text-blue-400 mt-1 flex-shrink-0" />
                  <div>
                    <h3 className="font-medium text-base text-white mb-2">Storage Locations</h3>
                    <div className="text-sm text-gray-300 space-y-2">
                      <p>
                        <strong className="text-white">Bearer tokens:</strong> <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">~/.fmcp/tokens/current_token.txt</code>
                      </p>
                      <p>
                        <strong className="text-white">Environment variables:</strong> <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">~/.fluidmcp/packages/{"{author}"}/{"{package}"}/{"{version}"}/metadata.json</code>
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Troubleshooting */}
          {activeItem === "troubleshooting" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">Support</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Troubleshooting</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  Diagnose and resolve common issues with FluidMCP.
                </p>
              </div>

              <div className="space-y-6">
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Diagnostic Commands</h3>
                  
                  <div className="space-y-4">
                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <h4 className="font-semibold text-base text-white mb-3">Validate Configuration</h4>
                      <p className="text-sm text-gray-300 mb-3">Check for configuration errors:</p>
                      <CodeBlock language="bash">{`# Validate a config file
fluidmcp validate config.json --file

# Validate installed package
fluidmcp validate author/package@version`}</CodeBlock>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <h4 className="font-semibold text-base text-white mb-3">Enable Verbose Logging</h4>
                      <p className="text-sm text-gray-300 mb-3">Get detailed debug information:</p>
                      <CodeBlock language="bash">fluidmcp run config.json --file --start-server --verbose</CodeBlock>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <h4 className="font-semibold text-base text-white mb-3">Check Server Status</h4>
                      <CodeBlock language="bash">{`# Via API
curl http://localhost:8099/api/servers

# Check specific server
curl http://localhost:8099/api/servers/my-server/status`}</CodeBlock>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <h4 className="font-semibold text-base text-white mb-3">View Server Logs</h4>
                      <CodeBlock language="bash">curl http://localhost:8099/api/servers/my-server/logs?lines=100</CodeBlock>
                    </div>

                    <div className="border border-[#2A2D36] rounded-lg p-5 bg-transparent">
                      <h4 className="font-semibold text-base text-white mb-3">Health Check</h4>
                      <p className="text-sm text-gray-300 mb-3">Verify API server health and database connection:</p>
                      <CodeBlock language="bash">curl http://localhost:8099/health</CodeBlock>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Check System Requirements</h3>
                  <CodeBlock language="bash">{`# Check versions
fluidmcp --version
python --version
node --version
npx --version

# Verify commands are available
which python
which npx
which docker  # if using containers`}</CodeBlock>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Port Conflicts</h3>
                  <p className="text-sm text-gray-300 mb-4">If port 8099 is already in use:</p>
                  
                  <div className="space-y-4">
                    <div>
                      <h4 className="font-semibold text-base text-white mb-3">Find Process Using Port</h4>
                      <CodeBlock language="bash">{`# Linux/Mac
lsof -i :8099

# Windows
netstat -ano | findstr :8099`}</CodeBlock>
                    </div>

                    <div className="mt-4">
                      <h4 className="font-semibold text-base text-white mb-3">Use Custom Port</h4>
                      <CodeBlock language="bash">{`# Set via environment variable
export FMCP_PORT=8080
fluidmcp run config.json --file --start-server

# Force reload (kills existing process)
fluidmcp run config.json --file --start-server --force-reload`}</CodeBlock>
                    </div>
                  </div>
                </div>

                <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-5">
                  <div className="flex items-start gap-3">
                    <AlertCircle className="h-6 w-6 text-yellow-400 mt-0.5 flex-shrink-0" />
                    <div>
                      <h3 className="font-semibold text-base text-white mb-3">Validation Checks</h3>
                      <p className="text-sm text-gray-300 mb-3">The validate command checks:</p>
                      <ul className="space-y-2 text-sm text-gray-300">
                        <li className="flex items-start gap-2">
                          <span className="text-yellow-400 mt-1">✓</span>
                          <span>Configuration file syntax and structure</span>
                        </li>
                        <li className="flex items-start gap-2">
                          <span className="text-yellow-400 mt-1">✓</span>
                          <span>Command availability in system PATH</span>
                        </li>
                        <li className="flex items-start gap-2">
                          <span className="text-yellow-400 mt-1">✓</span>
                          <span>Required environment variables</span>
                        </li>
                        <li className="flex items-start gap-2">
                          <span className="text-yellow-400 mt-1">✓</span>
                          <span>Metadata file existence and format</span>
                        </li>
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Common Issues and Solutions */}
          {activeItem === "common-issues" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">Support</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Common Issues and Solutions</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  Quick fixes for frequently encountered problems.
                </p>
              </div>

              <div className="space-y-6">
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white flex items-center gap-2">
                    <AlertCircle className="h-6 w-6 text-red-400" />
                    Installation Issues
                  </h3>
                  
                  <div className="space-y-5">
                    <div className="border-l-4 border-red-500/50 pl-4">
                      <h4 className="font-semibold text-base text-white mb-2">Package not found</h4>
                      <p className="text-sm text-gray-300 mb-3"><strong>Problem:</strong> Error when installing a package</p>
                      <p className="text-sm text-gray-300 mb-3"><strong>Solution:</strong></p>
                      <CodeBlock language="bash">{`# Verify package format
fluidmcp install author/package@version

# Check MCP registry configuration
echo $MCP_FETCH_URL
echo $MCP_TOKEN

# Try verbose mode for details
fluidmcp install author/package@version --verbose`}</CodeBlock>
                    </div>

                    <div className="border-l-4 border-red-500/50 pl-4">
                      <h4 className="font-semibold text-base text-white mb-2">Command not found: npx</h4>
                      <p className="text-sm text-gray-300 mb-3"><strong>Problem:</strong> npm-based MCP servers fail to start</p>
                      <p className="text-sm text-gray-300 mb-3"><strong>Solution:</strong></p>
                      <CodeBlock language="bash">{`# Install Node.js and npm
# Ubuntu/Debian
sudo apt-get install nodejs npm

# macOS
brew install node

# Verify installation
node --version
npx --version`}</CodeBlock>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white flex items-center gap-2">
                    <Server className="h-6 w-6 text-yellow-400" />
                    Server Runtime Issues
                  </h3>
                  
                  <div className="space-y-5">
                    <div className="border-l-4 border-yellow-500/50 pl-4">
                      <h4 className="font-semibold text-base text-white mb-2">Server fails to start</h4>
                      <p className="text-sm text-gray-300 mb-3"><strong>Problem:</strong> MCP server doesn\'t start or crashes immediately</p>
                      <p className="text-sm text-gray-300 mb-3"><strong>Solution:</strong></p>
                      <CodeBlock language="bash">{`# 1. Validate configuration
fluidmcp validate config.json --file

# 2. Check server logs
curl http://localhost:8099/api/servers/my-server/logs

# 3. Verify environment variables
fluidmcp edit-env author/package@version

# 4. Test server manually
npx -y @modelcontextprotocol/server-filesystem /tmp`}</CodeBlock>
                    </div>

                    <div className="border-l-4 border-yellow-500/50 pl-4">
                      <h4 className="font-semibold text-base text-white mb-2">Port already in use</h4>
                      <p className="text-sm text-gray-300 mb-3"><strong>Problem:</strong> Address already in use error</p>
                      <p className="text-sm text-gray-300 mb-3"><strong>Solution:</strong></p>
                      <CodeBlock language="bash">{`# Option 1: Force reload (kills existing process)
fluidmcp run config.json --file --start-server --force-reload

# Option 2: Use different port
export FMCP_PORT=8080
fluidmcp run config.json --file --start-server

# Option 3: Kill existing process manually
lsof -ti:8099 | xargs kill -9`}</CodeBlock>
                    </div>

                    <div className="border-l-4 border-yellow-500/50 pl-4">
                      <h4 className="font-semibold text-base text-white mb-2">Server shows as "running" but doesn\'t respond</h4>
                      <p className="text-sm text-gray-300 mb-3"><strong>Problem:</strong> Server process exists but isn't functional</p>
                      <p className="text-sm text-gray-300 mb-3"><strong>Solution:</strong></p>
                      <CodeBlock language="bash">{`# Restart the server
curl -X POST http://localhost:8099/api/servers/my-server/restart

# Or stop and start again
curl -X POST http://localhost:8099/api/servers/my-server/stop
curl -X POST http://localhost:8099/api/servers/my-server/start`}</CodeBlock>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white flex items-center gap-2">
                    <Key className="h-6 w-6 text-blue-400" />
                    Authentication Issues
                  </h3>
                  
                  <div className="space-y-5">
                    <div className="border-l-4 border-blue-500/50 pl-4">
                      <h4 className="font-semibold text-base text-white mb-2">401 Unauthorized error</h4>
                      <p className="text-sm text-gray-300 mb-3"><strong>Problem:</strong> API requests fail with authentication error</p>
                      <p className="text-sm text-gray-300 mb-3"><strong>Solution:</strong></p>
                      <CodeBlock language="bash">{`# Show current token
fluidmcp token show

# Use token in requests
curl -H "Authorization: Bearer YOUR_TOKEN" \\
  http://localhost:8099/api/servers

# Generate new token if lost
fluidmcp token regenerate`}</CodeBlock>
                    </div>

                    <div className="border-l-4 border-blue-500/50 pl-4">
                      <h4 className="font-semibold text-base text-white mb-2">Missing API key for MCP server</h4>
                      <p className="text-sm text-gray-300 mb-3"><strong>Problem:</strong> Server requires API key but none is provided</p>
                      <p className="text-sm text-gray-300 mb-3"><strong>Solution:</strong></p>
                      <CodeBlock language="bash">{`# Update environment variables
curl -X PUT http://localhost:8099/api/servers/my-server/instance/env \\
  -H "Content-Type: application/json" \\
  -d \'{"API_KEY": "your-actual-key"}\'

# Or edit via CLI
fluidmcp edit-env author/package@version`}</CodeBlock>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white flex items-center gap-2">
                    <Wrench className="h-6 w-6 text-green-400" />
                    Tool Execution Issues
                  </h3>
                  
                  <div className="space-y-5">
                    <div className="border-l-4 border-green-500/50 pl-4">
                      <h4 className="font-semibold text-base text-white mb-2">Tool not found</h4>
                      <p className="text-sm text-gray-300 mb-3"><strong>Problem:</strong> Trying to execute a tool that doesn\'t exist</p>
                      <p className="text-sm text-gray-300 mb-3"><strong>Solution:</strong></p>
                      <CodeBlock language="bash">{`# List available tools for the server
curl http://localhost:8099/api/servers/my-server/tools

# Verify exact tool name
curl http://localhost:8099/api/servers/my-server/tools | jq \'.tools[].name\'`}</CodeBlock>
                    </div>

                    <div className="border-l-4 border-green-500/50 pl-4">
                      <h4 className="font-semibold text-base text-white mb-2">Tool execution timeout</h4>
                      <p className="text-sm text-gray-300 mb-3"><strong>Problem:</strong> Tool takes too long to execute</p>
                      <p className="text-sm text-gray-300 mb-3"><strong>Solution:</strong> Check server logs for errors and verify the operation is valid:</p>
                      <CodeBlock language="bash">curl http://localhost:8099/api/servers/my-server/logs?lines=50</CodeBlock>
                    </div>
                  </div>
                </div>

                <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-5 flex items-start gap-4">
                  <BookOpen className="h-6 w-6 text-blue-400 mt-1 flex-shrink-0" />
                  <div>
                    <h3 className="font-medium text-base text-white mb-2">Still Having Issues?</h3>
                    <p className="text-sm text-gray-300 mb-3">
                      If these solutions don\'t help:
                    </p>
                    <ul className="space-y-2 text-sm text-gray-300">
                      <li className="flex items-start gap-2">
                        <span className="text-blue-400 mt-1">•</span>
                        <span>Check logs with <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">--verbose</code> flag</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="text-blue-400 mt-1">•</span>
                        <span>Review the <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">/health</code> endpoint for system status</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="text-blue-400 mt-1">•</span>
                        <span>Report issues on GitHub with full error logs</span>
                      </li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* FAQ */}
          {activeItem === "faq" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-5 duration-300">
              <div className="border-b border-[#1F2228] pb-6">
                <Badge className="mb-3 bg-blue-500/10 text-blue-400 border-none text-xs">Support</Badge>
                <h1 className="text-4xl font-bold tracking-tight text-white">Frequently Asked Questions</h1>
                <p className="text-lg text-gray-300 mt-4 leading-relaxed">
                  Answers to common questions about FluidMCP.
                </p>
              </div>

              <div className="space-y-6">
                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">General</h3>
                  
                  <div className="space-y-5">
                    <div>
                      <h4 className="font-semibold text-lg text-white mb-3">What is FluidMCP?</h4>
                      <p className="text-sm text-gray-300 leading-relaxed">
                        FluidMCP is a unified gateway for managing and orchestrating multiple Model Context Protocol (MCP) servers. 
                        It provides a FastAPI-based REST API that allows you to install, configure, and run MCP servers from a single 
                        interface, with features like authentication, monitoring, and centralized configuration management.
                      </p>
                    </div>

                    <div>
                      <h4 className="font-semibold text-lg text-white mb-3">What are MCP servers?</h4>
                      <p className="text-sm text-gray-300 leading-relaxed">
                        MCP (Model Context Protocol) servers are services that implement the MCP specification to provide tools and 
                        capabilities that AI models can use. They expose functions like file system access, web search, database queries, 
                        and more through a standardized interface.
                      </p>
                    </div>

                    <div>
                      <h4 className="font-semibold text-lg text-white mb-3">Do I need to know Python to use FluidMCP?</h4>
                      <p className="text-sm text-gray-300 leading-relaxed">
                        No. While FluidMCP is built with Python, you can use it entirely through the CLI commands without writing any Python code. 
                        The FastAPI gateway also provides a user-friendly web interface and REST API that can be accessed from any language.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Installation & Setup</h3>
                  
                  <div className="space-y-5">
                    <div>
                      <h4 className="font-semibold text-lg text-white mb-3">Which Python version is required?</h4>
                      <p className="text-sm text-gray-300 leading-relaxed mb-3">
                        FluidMCP requires Python 3.8 or higher. Check your version with:
                      </p>
                      <CodeBlock>python --version</CodeBlock>
                    </div>

                    <div>
                      <h4 className="font-semibold text-lg text-white mb-3">Do I need Node.js installed?</h4>
                      <p className="text-sm text-gray-300 leading-relaxed">
                        Node.js is optional but recommended if you want to use npm-based MCP servers (which many official MCP servers are). 
                        You\'ll need Node.js 16+ and the <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">npx</code> command available.
                      </p>
                    </div>

                    <div>
                      <h4 className="font-semibold text-lg text-white mb-3">Can I run FluidMCP in Docker?</h4>
                      <p className="text-sm text-gray-300 leading-relaxed mb-3">
                        Yes. A Dockerfile is provided in the repository:
                      </p>
                      <CodeBlock language="bash">{`docker build -t fluidmcp .
docker run -p 8099:8099 fluidmcp`}</CodeBlock>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Configuration</h3>
                  
                  <div className="space-y-5">
                    <div>
                      <h4 className="font-semibold text-lg text-white mb-3">What\'s the difference between single package and multi-server mode?</h4>
                      <p className="text-sm text-gray-300 leading-relaxed">
                        <strong className="text-white">Single package mode:</strong> Install and run one MCP server at a time using 
                        <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400 mx-1">fluidmcp run author/package@version</code>
                        <br/><br/>
                        <strong className="text-white">Multi-server mode:</strong> Define multiple MCP servers in a configuration file and run them all together using 
                        <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400 mx-1">fluidmcp run config.json --file</code>
                      </p>
                    </div>

                    <div>
                      <h4 className="font-semibold text-lg text-white mb-3">How do I change the default port?</h4>
                      <p className="text-sm text-gray-300 leading-relaxed mb-3">
                        Set the <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">FMCP_PORT</code> environment variable:
                      </p>
                      <CodeBlock language="bash">{`export FMCP_PORT=8080
fluidmcp run config.json --file --start-server`}</CodeBlock>
                    </div>

                    <div>
                      <h4 className="font-semibold text-lg text-white mb-3">Can I use S3 for centralized configuration?</h4>
                      <p className="text-sm text-gray-300 leading-relaxed mb-3">
                        Yes. FluidMCP supports S3-based configuration management for enterprise deployments:
                      </p>
                      <CodeBlock language="bash">{`# Run from S3 URL
fluidmcp run "https://bucket.s3.amazonaws.com/config.json" --s3 --start-server

# Or use master mode
fluidmcp run all --master --start-server`}</CodeBlock>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Security</h3>
                  
                  <div className="space-y-5">
                    <div>
                      <h4 className="font-semibold text-lg text-white mb-3">Is FluidMCP secure for production use?</h4>
                      <p className="text-sm text-gray-300 leading-relaxed">
                        Yes, when configured properly. Always use <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">--secure</code> mode 
                        for production deployments, which enables bearer token authentication. Store API keys securely using environment variables, 
                        and restrict CORS origins to trusted domains only.
                      </p>
                    </div>

                    <div>
                      <h4 className="font-semibold text-lg text-white mb-3">Where are tokens stored?</h4>
                      <p className="text-sm text-gray-300 leading-relaxed">
                        Bearer tokens are saved to <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">~/.fmcp/tokens/current_token.txt</code> 
                        with file permissions set to 600 (owner read/write only) for security.
                      </p>
                    </div>

                    <div>
                      <h4 className="font-semibold text-lg text-white mb-3">How do I rotate API keys?</h4>
                      <p className="text-sm text-gray-300 leading-relaxed mb-3">
                        For bearer tokens, use the token management commands. For MCP server API keys, update them via the API or edit-env command:
                      </p>
                      <CodeBlock language="bash">{`# Regenerate bearer token
fluidmcp token regenerate

# Update MCP server API keys
curl -X PUT http://localhost:8099/api/servers/my-server/instance/env \\
  -H "Content-Type: application/json" \\
  -d \'{"API_KEY": "new-value"}\'`}</CodeBlock>
                    </div>
                  </div>
                </div>

                <div className="bg-transparent border border-[#2A2D36] rounded-lg p-6">
                  <h3 className="text-2xl font-medium mb-5 text-white">Performance & Scaling</h3>
                  
                  <div className="space-y-5">
                    <div>
                      <h4 className="font-semibold text-lg text-white mb-3">How many MCP servers can I run simultaneously?</h4>
                      <p className="text-sm text-gray-300 leading-relaxed">
                        There\'s no hard limit, but practical limits depend on your system resources (CPU, memory, network). Each MCP server 
                        runs as a separate process. Monitor resource usage via the <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">/metrics</code> endpoint.
                      </p>
                    </div>

                    <div>
                      <h4 className="font-semibold text-lg text-white mb-3">Does FluidMCP support clustering or high availability?</h4>
                      <p className="text-sm text-gray-300 leading-relaxed">
                        FluidMCP can be run in multiple instances behind a load balancer. Use MongoDB for persistence to share state across instances. 
                        Configure CORS and authentication appropriately for distributed deployments.
                      </p>
                    </div>

                    <div>
                      <h4 className="font-semibold text-lg text-white mb-3">What monitoring is available?</h4>
                      <p className="text-sm text-gray-300 leading-relaxed">
                        FluidMCP provides Prometheus-compatible metrics at <code className="bg-[#1A1D26] px-2 py-1 rounded text-blue-400">/metrics</code> 
                        including request counts, latencies, server uptime, and resource utilization. The frontend dashboard provides real-time visualization 
                        of server status and logs.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="bg-blue-500/5 border border-blue-500/20 rounded-lg p-5 flex items-start gap-4">
                  <HelpCircle className="h-6 w-6 text-blue-400 mt-1 flex-shrink-0" />
                  <div>
                    <h3 className="font-medium text-base text-white mb-2">More Questions?</h3>
                    <p className="text-sm text-gray-300">
                      Can\'t find what you\'re looking for? Visit our GitHub repository to:
                    </p>
                    <ul className="space-y-2 text-sm text-gray-300 mt-3">
                      <li className="flex items-start gap-2">
                        <span className="text-blue-400 mt-1">•</span>
                        <span>Browse existing issues and discussions</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="text-blue-400 mt-1">•</span>
                        <span>Report bugs or request features</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="text-blue-400 mt-1">•</span>
                        <span>Contribute to the documentation</span>
                      </li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Footer */}
      <Footer />

      {/* Scroll to top button */}
      {showScrollTop && (
        <button
          onClick={scrollToTop}
          className="fixed bottom-6 right-6 bg-white text-black p-3 rounded-full shadow-lg hover:bg-gray-100 transition-colors"
          aria-label="Scroll to top"
        >
          <ArrowUp className="h-5 w-5" />
        </button>
      )}
    </div>
  )
}