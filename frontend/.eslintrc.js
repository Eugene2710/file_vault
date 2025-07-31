module.exports = {
    extends: [
      'react-app',
      'react-app/jest',
      'prettier',
    ],
    rules: {
      // General rules
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      'no-debugger': 'warn',
      'prefer-const': 'error',
      'no-var': 'error',
      
      // React specific rules
      'react-hooks/exhaustive-deps': 'warn',
      
      // Import organization
      'import/order': [
        'error',
        {
          groups: [
            'builtin',
            'external',
            'internal',
            'parent',
            'sibling',
            'index',
          ],
          'newlines-between': 'always',
          alphabetize: {
            order: 'asc',
            caseInsensitive: true,
          },
        },
      ],
    },
    ignorePatterns: ['build/', 'dist/', 'node_modules/'],
  };