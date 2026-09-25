import {
  queryDatabase,
  voiceQuery,
  clarifyQuery,
  confirmQuery,
  getQuery,
  getSchema,
  getHistory,
  ApiError,
} from '@/services/api';

export {
  queryDatabase,
  voiceQuery,
  clarifyQuery,
  confirmQuery,
  getQuery,
  getSchema,
  getHistory,
  ApiError,
};

// Aliases for existing component imports
export const submitQuery = queryDatabase;
export const submitVoiceQuery = voiceQuery;
export const submitClarification = clarifyQuery;
export const confirmMutation = confirmQuery;
export const fetchSchema = getSchema;
export const fetchHistory = getHistory;
