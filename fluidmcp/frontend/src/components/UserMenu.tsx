import { useEffect, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { Button } from './ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';
import { Avatar, AvatarFallback, AvatarImage } from './ui/avatar';

export function UserMenu() {
  const { user, authConfig, loading, checkAuth, logout, isAuthenticated } = useAuth();
  const [authChecked, setAuthChecked] = useState(false);

  // Check auth only once on mount
  useEffect(() => {
    if (!authChecked) {
      checkAuth().finally(() => setAuthChecked(true));
    }
  }, [authChecked, checkAuth]);

  // Don't show anything until auth check is complete
  if (!authChecked || loading) {
    return <div className="animate-pulse h-8 w-8 rounded-full bg-muted" />;
  }

  // OAuth disabled - hide the menu entirely
  if (!authConfig?.enabled) {
    return null;
  }

  // Not authenticated but OAuth is enabled - show login button
  if (!isAuthenticated) {
    return (
      <Button
        onClick={() => window.location.href = '/auth/login'}
        variant="outline"
        size="sm"
      >
        Sign In
      </Button>
    );
  }

  // Authenticated - show user menu
  const initials = user?.name
    ?.split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase() || '??';

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="relative h-8 w-8 rounded-full">
          <Avatar className="h-8 w-8">
            {user?.picture && <AvatarImage src={user.picture} alt={user?.name} />}
            <AvatarFallback className="bg-zinc-700 text-white text-xs font-semibold">
              {initials}
            </AvatarFallback>
          </Avatar>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-56" align="end" forceMount>
        <DropdownMenuLabel className="font-normal">
          <div className="flex flex-col space-y-1">
            <p className="text-sm font-medium leading-none">{user?.name}</p>
            <p className="text-xs leading-none text-muted-foreground">
              {user?.email}
            </p>
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={logout}>
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
