/**
 * Phase 1 Frontend Integration - React/TypeScript Example
 *
 * This file shows how to integrate the Ambient Presence and Proactive Intervention
 * systems into your frontend application.
 */

import { useEffect, useState, useCallback } from 'react';

// ============================================================================
// Type Definitions
// ============================================================================

interface QuickAction {
  id: string;
  label: string;
  action_type: string;
  icon: string;
  context: Record<string, any>;
}

interface Intervention {
  intervention_type: string;
  priority: number;
  title: string;
  message: string;
  action: string;
  timing: string;
  context: Record<string, any>;
}

interface NotificationPreferences {
  dnd_enabled: boolean;
  quiet_hours_start?: string;
  quiet_hours_end?: string;
  max_notifications_per_day: number;
  enabled_intervention_types?: string[];
  disabled_intervention_types?: string[];
}

// ============================================================================
// API Client
// ============================================================================

class LyoPhase1Client {
  private baseUrl: string;
  private authToken: string;

  constructor(baseUrl: string = 'http://localhost:8000', authToken: string = '') {
    this.baseUrl = baseUrl;
    this.authToken = authToken;
  }

  setAuthToken(token: string) {
    this.authToken = token;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.authToken}`,
        ...options.headers,
      },
    });

    if (!response.ok) {
      throw new Error(`API Error: ${response.statusText}`);
    }

    return response.json();
  }

  // Ambient Presence API
  async updatePresence(data: {
    page: string;
    topic?: string;
    content_id?: string;
    time_on_page: number;
    scroll_count: number;
    mouse_hesitations: number;
  }) {
    return this.request('/api/v1/ambient/presence/update', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async checkInlineHelp(data: {
    user_behavior: Record<string, any>;
    current_context: Record<string, any>;
  }) {
    return this.request<{ should_show: boolean; help_message?: string }>('/api/v1/ambient/inline-help/check', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async logInlineHelp(data: {
    help_type: string;
    help_text: string;
    page: string;
    topic?: string;
    content_id?: string;
  }) {
    return this.request<{ log_id: number }>('/api/v1/ambient/inline-help/log', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async recordHelpResponse(logId: number, response: 'accepted' | 'dismissed' | 'ignored') {
    return this.request('/api/v1/ambient/inline-help/response', {
      method: 'POST',
      body: JSON.stringify({ help_log_id: logId, user_response: response }),
    });
  }

  async getQuickActions(page: string, context: Record<string, any> = {}) {
    return this.request<{ actions: QuickAction[] }>('/api/v1/ambient/quick-actions', {
      method: 'POST',
      body: JSON.stringify({ current_page: page, current_content: context }),
    });
  }

  // Proactive Intervention API
  async getInterventions() {
    return this.request<{ interventions: Intervention[]; count: number }>('/api/v1/proactive/interventions');
  }

  async logIntervention(intervention: Intervention) {
    return this.request('/api/v1/proactive/interventions/log', {
      method: 'POST',
      body: JSON.stringify(intervention),
    });
  }

  async recordInterventionResponse(logId: number, response: 'engaged' | 'dismissed' | 'ignored' | 'snoozed') {
    return this.request('/api/v1/proactive/interventions/response', {
      method: 'POST',
      body: JSON.stringify({ intervention_log_id: logId, user_response: response }),
    });
  }

  async getNotificationPreferences() {
    return this.request<NotificationPreferences>('/api/v1/proactive/preferences');
  }

  async updateNotificationPreferences(prefs: Partial<NotificationPreferences>) {
    return this.request('/api/v1/proactive/preferences', {
      method: 'PUT',
      body: JSON.stringify(prefs),
    });
  }
}

// ============================================================================
// React Hook: Presence Tracker
// ============================================================================

export function usePresenceTracker(client: LyoPhase1Client, page: string, topic?: string, contentId?: string) {
  const [startTime] = useState(Date.now());
  const [scrollCount, setScrollCount] = useState(0);

  useEffect(() => {
    const handleScroll = () => setScrollCount(prev => prev + 1);
    window.addEventListener('scroll', handleScroll);

    // Update presence every 10 seconds
    const interval = setInterval(() => {
      const timeOnPage = (Date.now() - startTime) / 1000;
      client.updatePresence({
        page,
        topic,
        content_id: contentId,
        time_on_page: timeOnPage,
        scroll_count: scrollCount,
        mouse_hesitations: 0,
      }).catch(console.error);
    }, 10000);

    return () => {
      window.removeEventListener('scroll', handleScroll);
      clearInterval(interval);
    };
  }, [client, page, topic, contentId, scrollCount, startTime]);
}

// ============================================================================
// React Hook: Inline Help
// ============================================================================

export function useInlineHelp(client: LyoPhase1Client, page: string, topic?: string) {
  const [helpMessage, setHelpMessage] = useState<string | null>(null);
  const [helpLogId, setHelpLogId] = useState<number | null>(null);
  const [startTime] = useState(Date.now());
  const [scrollCount, setScrollCount] = useState(0);

  useEffect(() => {
    const handleScroll = () => setScrollCount(prev => prev + 1);
    window.addEventListener('scroll', handleScroll);

    // Check for inline help every 15 seconds
    const interval = setInterval(async () => {
      try {
        const timeOnSection = (Date.now() - startTime) / 1000;
        const result = await client.checkInlineHelp({
          user_behavior: { time_on_section: timeOnSection, scroll_count: scrollCount },
          current_context: { page, topic },
        });

        if (result.should_show && result.help_message) {
          setHelpMessage(result.help_message);

          // Log that help was shown
          const logResult = await client.logInlineHelp({
            help_type: 'contextual',
            help_text: result.help_message,
            page,
            topic,
          });
          setHelpLogId(logResult.log_id);
        }
      } catch (error) {
        console.error('Error checking inline help:', error);
      }
    }, 15000);

    return () => {
      window.removeEventListener('scroll', handleScroll);
      clearInterval(interval);
    };
  }, [client, page, topic, scrollCount, startTime]);

  const acceptHelp = useCallback(async () => {
    if (helpLogId) {
      await client.recordHelpResponse(helpLogId, 'accepted');
    }
    // Navigate to chat or show help dialog
    console.log('User accepted help:', helpMessage);
  }, [client, helpLogId, helpMessage]);

  const dismissHelp = useCallback(async () => {
    if (helpLogId) {
      await client.recordHelpResponse(helpLogId, 'dismissed');
    }
    setHelpMessage(null);
    setHelpLogId(null);
  }, [client, helpLogId]);

  return { helpMessage, acceptHelp, dismissHelp };
}

// ============================================================================
// React Hook: Proactive Interventions
// ============================================================================

export function useProactiveInterventions(client: LyoPhase1Client) {
  const [interventions, setInterventions] = useState<Intervention[]>([]);

  const checkInterventions = useCallback(async () => {
    try {
      const result = await client.getInterventions();
      if (result.count > 0) {
        setInterventions(result.interventions);
      }
    } catch (error) {
      console.error('Error checking interventions:', error);
    }
  }, [client]);

  useEffect(() => {
    // Check immediately
    checkInterventions();

    // Check every minute
    const interval = setInterval(checkInterventions, 60000);

    // Check on window focus
    const handleFocus = () => checkInterventions();
    window.addEventListener('focus', handleFocus);

    return () => {
      clearInterval(interval);
      window.removeEventListener('focus', handleFocus);
    };
  }, [checkInterventions]);

  const respondToIntervention = useCallback(async (
    intervention: Intervention,
    logId: number,
    response: 'engaged' | 'dismissed' | 'snoozed'
  ) => {
    await client.recordInterventionResponse(logId, response);

    if (response === 'engaged') {
      // Navigate to the action
      console.log('User engaged with intervention:', intervention.action);
      // router.push(intervention.action);
    }

    // Remove from list
    setInterventions(prev => prev.filter(i => i !== intervention));
  }, [client]);

  return { interventions, respondToIntervention };
}

// ============================================================================
// React Hook: Quick Actions (Cmd+K Palette)
// ============================================================================

export function useQuickActions(client: LyoPhase1Client, page: string, context: Record<string, any> = {}) {
  const [actions, setActions] = useState<QuickAction[]>([]);
  const [isOpen, setIsOpen] = useState(false);

  const loadActions = useCallback(async () => {
    try {
      const result = await client.getQuickActions(page, context);
      setActions(result.actions);
    } catch (error) {
      console.error('Error loading quick actions:', error);
    }
  }, [client, page, context]);

  useEffect(() => {
    // Load actions when page/context changes
    if (isOpen) {
      loadActions();
    }
  }, [isOpen, loadActions]);

  useEffect(() => {
    // Handle Cmd+K / Ctrl+K
    const handleKeydown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsOpen(prev => !prev);
      }
    };

    window.addEventListener('keydown', handleKeydown);
    return () => window.removeEventListener('keydown', handleKeydown);
  }, []);

  const executeAction = useCallback((action: QuickAction) => {
    console.log('Executing action:', action);
    setIsOpen(false);

    // Handle different action types
    switch (action.action_type) {
      case 'ask_anything':
        // Open chat
        break;
      case 'explain_concept':
        // Open chat with concept
        break;
      case 'practice_questions':
        // Generate practice questions
        break;
      // Add more cases as needed
    }
  }, []);

  return { actions, isOpen, setIsOpen, executeAction };
}

// ============================================================================
// React Components
// ============================================================================

// Component: Inline Help Tooltip
export function InlineHelpTooltip({ message, onAccept, onDismiss }: {
  message: string;
  onAccept: () => void;
  onDismiss: () => void;
}) {
  return (
    <div className="fixed bottom-4 right-4 bg-white shadow-lg rounded-lg p-4 max-w-sm border border-blue-200">
      <div className="flex items-start space-x-3">
        <div className="flex-shrink-0">
          <span className="text-2xl">💬</span>
        </div>
        <div className="flex-1">
          <p className="text-sm text-gray-700">{message}</p>
          <div className="mt-3 flex space-x-2">
            <button
              onClick={onAccept}
              className="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
            >
              Yes, help me
            </button>
            <button
              onClick={onDismiss}
              className="px-3 py-1 bg-gray-200 text-gray-700 text-sm rounded hover:bg-gray-300"
            >
              No thanks
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Component: Intervention Notification
export function InterventionNotification({ intervention, onEngage, onDismiss }: {
  intervention: Intervention;
  onEngage: () => void;
  onDismiss: () => void;
}) {
  return (
    <div className="fixed top-4 right-4 bg-white shadow-xl rounded-lg p-4 max-w-sm border border-purple-200 animate-slide-in">
      <div className="flex items-start space-x-3">
        <div className="flex-shrink-0">
          <span className="text-2xl">🎯</span>
        </div>
        <div className="flex-1">
          <h3 className="font-semibold text-gray-900">{intervention.title}</h3>
          <p className="text-sm text-gray-600 mt-1">{intervention.message}</p>
          <div className="mt-3 flex space-x-2">
            <button
              onClick={onEngage}
              className="px-3 py-1 bg-purple-600 text-white text-sm rounded hover:bg-purple-700"
            >
              Let's go
            </button>
            <button
              onClick={onDismiss}
              className="px-3 py-1 bg-gray-200 text-gray-700 text-sm rounded hover:bg-gray-300"
            >
              Later
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Component: Quick Actions Palette (Cmd+K)
export function QuickActionsPalette({ actions, isOpen, onClose, onExecute }: {
  actions: QuickAction[];
  isOpen: boolean;
  onClose: () => void;
  onExecute: (action: QuickAction) => void;
}) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-start justify-center pt-20 z-50">
      <div className="bg-white rounded-lg shadow-2xl w-full max-w-2xl">
        <div className="p-4">
          <input
            type="text"
            placeholder="Type a command or search..."
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            autoFocus
          />
        </div>
        <div className="border-t border-gray-200 max-h-96 overflow-y-auto">
          {actions.map((action) => (
            <button
              key={action.id}
              onClick={() => onExecute(action)}
              className="w-full px-4 py-3 text-left hover:bg-gray-100 flex items-center space-x-3 border-b border-gray-100"
            >
              <span className="text-xl">{action.icon}</span>
              <span className="text-gray-700">{action.label}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="fixed inset-0 -z-10" onClick={onClose}></div>
    </div>
  );
}

// ============================================================================
// Example Usage in App Component
// ============================================================================

export function ExampleAppComponent() {
  const [client] = useState(() => new LyoPhase1Client('http://localhost:8000', 'YOUR_AUTH_TOKEN'));

  // Track presence
  usePresenceTracker(client, 'lesson', 'calculus', 'lesson-123');

  // Inline help
  const { helpMessage, acceptHelp, dismissHelp } = useInlineHelp(client, 'lesson', 'calculus');

  // Proactive interventions
  const { interventions, respondToIntervention } = useProactiveInterventions(client);

  // Quick actions
  const { actions, isOpen, setIsOpen, executeAction } = useQuickActions(client, 'lesson', {
    current_concept: 'Derivatives'
  });

  return (
    <div>
      {/* Your app content */}

      {/* Inline help tooltip */}
      {helpMessage && (
        <InlineHelpTooltip
          message={helpMessage}
          onAccept={acceptHelp}
          onDismiss={dismissHelp}
        />
      )}

      {/* Proactive interventions */}
      {interventions.map((intervention, i) => (
        <InterventionNotification
          key={i}
          intervention={intervention}
          onEngage={() => respondToIntervention(intervention, i, 'engaged')}
          onDismiss={() => respondToIntervention(intervention, i, 'dismissed')}
        />
      ))}

      {/* Quick actions palette */}
      <QuickActionsPalette
        actions={actions}
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        onExecute={executeAction}
      />
    </div>
  );
}

export default LyoPhase1Client;
