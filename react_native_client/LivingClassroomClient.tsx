/**
 * Living Classroom - React Native WebSocket Client
 * ===============================================
 *
 * Real-time WebSocket client for scene-by-scene streaming from the Living Classroom backend.
 * Cross-platform implementation for React Native (iOS & Android).
 *
 * Architecture: React Native Client ←→ WebSocket ←→ Scene Lifecycle Engine ←→ Multi-Agent System
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  Animated,
  Alert,
} from 'react-native';

// MARK: - TypeScript Interfaces (matching Python backend exactly)

interface ScenePayload {
  event_type: string;
  session_id: string;
  scene: Scene;
  component_count: number;
}

interface Scene {
  scene_id: string;
  scene_type: SceneType;
  components: Component[];
  priority: number;
  metadata?: SceneMetadata;
}

type SceneType = 'instruction' | 'challenge' | 'celebration' | 'correction' | 'reflection';

interface SceneMetadata {
  estimated_duration_ms?: number;
  difficulty_level?: string;
  concept_tags?: string[];
}

// MARK: - Component System (Server-Driven UI)

interface BaseComponent {
  component_id: string;
  type: ComponentType;
  priority: number;
  delay_ms?: number;
  isVisible?: boolean;
}

type ComponentType =
  | 'TeacherMessage'
  | 'StudentPrompt'
  | 'QuizCard'
  | 'CTAButton'
  | 'Celebration'
  | 'CodeEditor';

interface TeacherMessage extends BaseComponent {
  type: 'TeacherMessage';
  text: string;
  emotion?: string;
  audio_mood?: string;
  concept_tags?: string[];
}

interface QuizCard extends BaseComponent {
  type: 'QuizCard';
  question: string;
  options: QuizOption[];
  concept_id?: string;
}

interface QuizOption {
  id: string;
  label: string;
  is_correct: boolean;
}

interface CTAButton extends BaseComponent {
  type: 'CTAButton';
  label: string;
  action_intent: ActionIntent;
  style?: string;
}

type ActionIntent =
  | 'continue'
  | 'retry'
  | 'hint'
  | 'skip'
  | 'celebrate'
  | 'next_topic';

interface Celebration extends BaseComponent {
  type: 'Celebration';
  message: string;
  celebration_type: string;
  particle_effect?: boolean;
}

type Component = TeacherMessage | QuizCard | CTAButton | Celebration;

// MARK: - WebSocket Client Hook

export const useLivingClassroomClient = (userToken: string, sessionId?: string) => {
  const [isConnected, setIsConnected] = useState(false);
  const [currentScene, setCurrentScene] = useState<Scene | null>(null);
  const [components, setComponents] = useState<Component[]>([]);
  const [connectionState, setConnectionState] = useState<'disconnected' | 'connecting' | 'connected' | 'error'>('disconnected');
  const [lastError, setLastError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const sessionIdRef = useRef(sessionId || generateSessionId());
  const heartbeatRef = useRef<NodeJS.Timeout | null>(null);

  // MARK: - Connection Management

  const connect = useCallback(async () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setConnectionState('connecting');

    const baseURL = 'wss://lyo-production.up.railway.app';
    const wsURL = `${baseURL}/api/v1/classroom/ws/connect`;

    try {
      const websocket = new WebSocket(wsURL, [], {
        headers: {
          'Authorization': `Bearer ${userToken}`,
          'X-Session-ID': sessionIdRef.current,
        }
      });

      websocket.onopen = () => {
        console.log('🎭 Living Classroom WebSocket connected - Session:', sessionIdRef.current);
        setIsConnected(true);
        setConnectionState('connected');
        setLastError(null);
        startHeartbeat();
      };

      websocket.onmessage = (event) => {
        handleMessage(event.data);
      };

      websocket.onerror = (error) => {
        console.error('❌ WebSocket error:', error);
        handleConnectionError('Connection error occurred');
      };

      websocket.onclose = (event) => {
        console.log('👋 WebSocket closed:', event.code, event.reason);
        setIsConnected(false);
        setConnectionState('disconnected');
        stopHeartbeat();

        // Attempt reconnection if not intentional close
        if (event.code !== 1000) {
          setTimeout(() => {
            if (connectionState !== 'disconnected') {
              setConnectionState('connecting');
              connect();
            }
          }, 3000);
        }
      };

      wsRef.current = websocket;

    } catch (error) {
      handleConnectionError(`Failed to connect: ${error}`);
    }
  }, [userToken, connectionState]);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close(1000, 'Client disconnect');
      wsRef.current = null;
    }
    stopHeartbeat();
    setIsConnected(false);
    setConnectionState('disconnected');
  }, []);

  // MARK: - Message Handling

  const handleMessage = useCallback(async (data: string) => {
    try {
      const message = JSON.parse(data);

      // Handle Scene Payload
      if (message.event_type === 'scene_start' && message.scene) {
        await handleScenePayload(message as ScenePayload);
        return;
      }

      // Handle generic messages
      switch (message.event_type) {
        case 'connection_established':
          console.log('✅ Living Classroom connection established');
          break;
        case 'scene_complete':
          console.log('✅ Scene complete');
          break;
        case 'error':
          setLastError(message.message || 'Unknown error');
          console.error('❌ Backend error:', message.message);
          break;
        default:
          console.log('📨 Unknown event:', message.event_type);
      }

    } catch (error) {
      console.error('❌ Failed to process message:', error);
    }
  }, []);

  const handleScenePayload = useCallback(async (payload: ScenePayload) => {
    console.log(`🎬 New scene received: ${payload.scene.scene_type} with ${payload.component_count} components`);

    setCurrentScene(payload.scene);

    // Initialize components with visibility false
    const newComponents = payload.scene.components.map(component => ({
      ...component,
      isVisible: false,
    }));

    setComponents(newComponents);

    // Start progressive rendering
    await progressivelyRenderComponents(newComponents);
  }, []);

  const progressivelyRenderComponents = useCallback(async (components: Component[]) => {
    const sortedComponents = [...components].sort((a, b) => a.priority - b.priority);

    for (let i = 0; i < sortedComponents.length; i++) {
      const component = sortedComponents[i];

      // Apply delay if specified
      if (component.delay_ms && component.delay_ms > 0) {
        await new Promise(resolve => setTimeout(resolve, component.delay_ms));
      }

      // Make component visible with animation
      setComponents(prevComponents =>
        prevComponents.map(comp =>
          comp.component_id === component.component_id
            ? { ...comp, isVisible: true }
            : comp
        )
      );

      // Small delay for animation
      await new Promise(resolve => setTimeout(resolve, 100));
    }
  }, []);

  const handleConnectionError = useCallback((errorMessage: string) => {
    setConnectionState('error');
    setIsConnected(false);
    setLastError(errorMessage);
  }, []);

  // MARK: - User Actions

  const sendUserAction = useCallback(async (intent: ActionIntent, data: Record<string, any> = {}) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket not connected');
    }

    const payload = {
      event_type: 'user_action',
      session_id: sessionIdRef.current,
      action_intent: intent,
      action_data: data,
      timestamp: new Date().toISOString(),
    };

    wsRef.current.send(JSON.stringify(payload));
    console.log('📤 User action sent:', intent);
  }, []);

  const submitQuizAnswer = useCallback(async (questionId: string, selectedOptionId: string, isCorrect: boolean) => {
    await sendUserAction('continue', {
      action_type: 'quiz_submit',
      question_id: questionId,
      selected_option: selectedOptionId,
      is_correct: isCorrect,
    });
  }, [sendUserAction]);

  const requestHint = useCallback(async () => {
    await sendUserAction('hint');
  }, [sendUserAction]);

  const continueLesson = useCallback(async () => {
    await sendUserAction('continue');
  }, [sendUserAction]);

  // MARK: - Heartbeat

  const startHeartbeat = useCallback(() => {
    heartbeatRef.current = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send('ping');
      }
    }, 30000); // 30 seconds
  }, []);

  const stopHeartbeat = useCallback(() => {
    if (heartbeatRef.current) {
      clearInterval(heartbeatRef.current);
      heartbeatRef.current = null;
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    isConnected,
    currentScene,
    components,
    connectionState,
    lastError,
    connect,
    disconnect,
    sendUserAction,
    submitQuizAnswer,
    requestHint,
    continueLesson,
  };
};

// MARK: - React Native Components

interface LivingClassroomViewProps {
  userToken: string;
  sessionId?: string;
}

export const LivingClassroomView: React.FC<LivingClassroomViewProps> = ({
  userToken,
  sessionId,
}) => {
  const client = useLivingClassroomClient(userToken, sessionId);

  useEffect(() => {
    client.connect();
  }, []);

  return (
    <View style={styles.container}>
      {/* Connection Status */}
      <View style={styles.statusBar}>
        <View style={[
          styles.statusIndicator,
          { backgroundColor: client.isConnected ? '#4CAF50' : '#F44336' }
        ]} />
        <Text style={styles.statusText}>
          {client.isConnected ? 'Connected' : 'Disconnected'}
        </Text>
        <Text style={styles.titleText}>Living Classroom</Text>
      </View>

      {/* Scene Components */}
      <ScrollView style={styles.scrollView} showsVerticalScrollIndicator={false}>
        {client.components.map((component) => (
          <ComponentView
            key={component.component_id}
            component={component}
            onQuizSubmit={client.submitQuizAnswer}
            onCTAPress={client.sendUserAction}
          />
        ))}
      </ScrollView>

      {/* Error Display */}
      {client.lastError && (
        <View style={styles.errorContainer}>
          <Text style={styles.errorText}>{client.lastError}</Text>
        </View>
      )}
    </View>
  );
};

interface ComponentViewProps {
  component: Component;
  onQuizSubmit: (questionId: string, selectedOptionId: string, isCorrect: boolean) => void;
  onCTAPress: (intent: ActionIntent) => void;
}

const ComponentView: React.FC<ComponentViewProps> = ({
  component,
  onQuizSubmit,
  onCTAPress,
}) => {
  const fadeAnim = useRef(new Animated.Value(component.isVisible ? 1 : 0)).current;

  useEffect(() => {
    Animated.timing(fadeAnim, {
      toValue: component.isVisible ? 1 : 0,
      duration: 500,
      useNativeDriver: true,
    }).start();
  }, [component.isVisible]);

  const renderComponent = () => {
    switch (component.type) {
      case 'TeacherMessage':
        return <TeacherMessageView message={component as TeacherMessage} />;
      case 'QuizCard':
        return <QuizCardView quiz={component as QuizCard} onSubmit={onQuizSubmit} />;
      case 'CTAButton':
        return <CTAButtonView button={component as CTAButton} onPress={onCTAPress} />;
      case 'Celebration':
        return <CelebrationView celebration={component as Celebration} />;
      default:
        return null;
    }
  };

  return (
    <Animated.View style={[styles.componentContainer, { opacity: fadeAnim }]}>
      {renderComponent()}
    </Animated.View>
  );
};

const TeacherMessageView: React.FC<{ message: TeacherMessage }> = ({ message }) => (
  <View style={styles.teacherMessage}>
    <Text style={styles.teacherMessageText}>{message.text}</Text>
    {message.emotion && (
      <Text style={styles.emotionText}>Emotion: {message.emotion}</Text>
    )}
  </View>
);

const QuizCardView: React.FC<{
  quiz: QuizCard;
  onSubmit: (questionId: string, selectedOptionId: string, isCorrect: boolean) => void;
}> = ({ quiz, onSubmit }) => {
  const [selectedOption, setSelectedOption] = useState<string | null>(null);

  const handleOptionSelect = (option: QuizOption) => {
    setSelectedOption(option.id);
    onSubmit(quiz.component_id, option.id, option.is_correct);
  };

  return (
    <View style={styles.quizCard}>
      <Text style={styles.quizQuestion}>{quiz.question}</Text>
      {quiz.options.map((option) => (
        <TouchableOpacity
          key={option.id}
          style={[
            styles.quizOption,
            selectedOption === option.id && styles.quizOptionSelected,
          ]}
          onPress={() => handleOptionSelect(option)}
        >
          <View style={[
            styles.radioButton,
            selectedOption === option.id && styles.radioButtonSelected,
          ]} />
          <Text style={styles.quizOptionText}>{option.label}</Text>
        </TouchableOpacity>
      ))}
    </View>
  );
};

const CTAButtonView: React.FC<{
  button: CTAButton;
  onPress: (intent: ActionIntent) => void;
}> = ({ button, onPress }) => (
  <TouchableOpacity
    style={styles.ctaButton}
    onPress={() => onPress(button.action_intent)}
  >
    <Text style={styles.ctaButtonText}>{button.label}</Text>
  </TouchableOpacity>
);

const CelebrationView: React.FC<{ celebration: Celebration }> = ({ celebration }) => {
  const scaleAnim = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    // Celebration animation
    Animated.sequence([
      Animated.timing(scaleAnim, { toValue: 1.2, duration: 300, useNativeDriver: true }),
      Animated.timing(scaleAnim, { toValue: 1, duration: 300, useNativeDriver: true }),
    ]).start();
  }, []);

  return (
    <Animated.View style={[styles.celebration, { transform: [{ scale: scaleAnim }] }]}>
      <Text style={styles.celebrationEmoji}>🎉</Text>
      <Text style={styles.celebrationText}>{celebration.message}</Text>
    </Animated.View>
  );
};

// MARK: - Utilities

const generateSessionId = (): string => {
  return 'session_' + Math.random().toString(36).substring(2, 15);
};

// MARK: - Styles

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F8F9FA',
  },
  statusBar: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    backgroundColor: '#FFFFFF',
    borderBottomWidth: 1,
    borderBottomColor: '#E9ECEF',
  },
  statusIndicator: {
    width: 12,
    height: 12,
    borderRadius: 6,
    marginRight: 8,
  },
  statusText: {
    fontSize: 12,
    color: '#6C757D',
    marginRight: 16,
  },
  titleText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#212529',
  },
  scrollView: {
    flex: 1,
    padding: 16,
  },
  componentContainer: {
    marginBottom: 16,
  },
  teacherMessage: {
    backgroundColor: '#E3F2FD',
    padding: 16,
    borderRadius: 12,
  },
  teacherMessageText: {
    fontSize: 16,
    color: '#1976D2',
    lineHeight: 24,
  },
  emotionText: {
    fontSize: 12,
    color: '#757575',
    marginTop: 8,
  },
  quizCard: {
    backgroundColor: '#E8F5E8',
    padding: 16,
    borderRadius: 12,
  },
  quizQuestion: {
    fontSize: 18,
    fontWeight: '600',
    color: '#2E7D32',
    marginBottom: 16,
  },
  quizOption: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    backgroundColor: '#F5F5F5',
    borderRadius: 8,
    marginBottom: 8,
  },
  quizOptionSelected: {
    backgroundColor: '#BBDEFB',
  },
  radioButton: {
    width: 20,
    height: 20,
    borderRadius: 10,
    borderWidth: 2,
    borderColor: '#9E9E9E',
    marginRight: 12,
  },
  radioButtonSelected: {
    borderColor: '#2196F3',
    backgroundColor: '#2196F3',
  },
  quizOptionText: {
    fontSize: 16,
    color: '#424242',
    flex: 1,
  },
  ctaButton: {
    backgroundColor: '#2196F3',
    padding: 16,
    borderRadius: 12,
    alignItems: 'center',
  },
  ctaButtonText: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  celebration: {
    backgroundColor: '#FFF9C4',
    padding: 20,
    borderRadius: 12,
    alignItems: 'center',
  },
  celebrationEmoji: {
    fontSize: 48,
    marginBottom: 8,
  },
  celebrationText: {
    fontSize: 18,
    fontWeight: '600',
    color: '#F57F17',
    textAlign: 'center',
  },
  errorContainer: {
    backgroundColor: '#FFEBEE',
    padding: 12,
    margin: 16,
    borderRadius: 8,
  },
  errorText: {
    fontSize: 14,
    color: '#D32F2F',
  },
});

export default LivingClassroomView;